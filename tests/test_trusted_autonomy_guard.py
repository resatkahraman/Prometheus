from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import SupervisorCreateRequest
from app.main import app, create_supervisor_command
from app.security.autonomy import (
    TRUSTED_AUTONOMY_DISABLED_DETAIL,
    TrustedAutonomyDisabledError,
)
from app.supervisor.models import SupervisorCommand, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class _UnusedAgent:
    async def run(self, _request):
        raise AssertionError("Agent bu güvenlik testinde çalışmamalı.")


def _service(
    tmp_path: Path,
    *,
    trusted_enabled: bool,
) -> SupervisorService:
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
        supervisor_trusted_autonomy_enabled=trusted_enabled,
    )
    tools = build_default_tool_registry(settings=settings)
    return SupervisorService(
        settings=settings,
        agent=_UnusedAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )


def _task() -> SupervisorTask:
    return SupervisorTask(
        id="TASK-001",
        title="Güvenlik görevi",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["Politika korunmalı."],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=[],
    )


def test_trusted_autonomy_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.supervisor_trusted_autonomy_enabled is False
    assert settings.supervisor_default_autonomy_mode == "task"


def test_trusted_default_requires_explicit_server_opt_in() -> None:
    with pytest.raises(
        ValidationError,
        match="SUPERVISOR_TRUSTED_AUTONOMY_ENABLED",
    ):
        Settings(
            _env_file=None,
            supervisor_default_autonomy_mode="trusted",
        )


def test_trusted_default_is_valid_with_explicit_server_opt_in() -> None:
    settings = Settings(
        _env_file=None,
        supervisor_default_autonomy_mode="trusted",
        supervisor_trusted_autonomy_enabled=True,
    )

    assert settings.supervisor_default_autonomy_mode == "trusted"
    assert settings.supervisor_trusted_autonomy_enabled is True


@pytest.mark.asyncio
async def test_service_rejects_unapproved_trusted_command(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, trusted_enabled=False)

    with pytest.raises(
        TrustedAutonomyDisabledError,
        match="SUPERVISOR_TRUSTED_AUTONOMY_ENABLED",
    ):
        await service.create(
            goal="Onaysız trusted komut oluştur",
            autonomy_mode="trusted",
        )

    assert await service.store.list() == []


@pytest.mark.asyncio
async def test_http_endpoint_returns_403_for_disabled_trusted_mode(
    tmp_path: Path,
) -> None:
    previous_supervisor = getattr(app.state, "supervisor", None)
    had_supervisor = hasattr(app.state, "supervisor")
    app.state.supervisor = _service(tmp_path, trusted_enabled=False)

    try:
        with pytest.raises(HTTPException) as captured:
            await create_supervisor_command(
                SupervisorCreateRequest(
                    goal="HTTP üzerinden trusted komut",
                    autonomy_mode="trusted",
                )
            )
    finally:
        if had_supervisor:
            app.state.supervisor = previous_supervisor
        else:
            delattr(app.state, "supervisor")

    assert captured.value.status_code == 403
    assert captured.value.detail == TRUSTED_AUTONOMY_DISABLED_DETAIL


@pytest.mark.asyncio
async def test_service_allows_trusted_command_after_explicit_opt_in(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, trusted_enabled=True)

    async def fake_complete_initial_plan(**kwargs):
        return await service.store.get(kwargs["command_id"])

    service._complete_initial_plan = fake_complete_initial_plan

    command = await service.create(
        goal="Açıkça izinli trusted komut",
        autonomy_mode="trusted",
    )

    assert command.autonomy_mode == "trusted"


def test_persisted_trusted_command_cannot_auto_execute_after_disable(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, trusted_enabled=False)
    command = SupervisorCommand(
        id="cmd-trusted-disabled",
        goal="Eski trusted komut",
        status="ready",
        autonomy_mode="trusted",
        plan_text="",
        tasks=[_task()],
    )

    allowed = service._auto_execution_allowed(
        command=command,
        task=command.tasks[0],
        tool_name="workspace_write",
        arguments={"path": "safe.txt", "content": "safe"},
    )

    assert allowed is False


def test_explicitly_enabled_trusted_command_can_auto_execute_low_risk_tool(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, trusted_enabled=True)
    command = SupervisorCommand(
        id="cmd-trusted-enabled",
        goal="İzinli trusted komut",
        status="ready",
        autonomy_mode="trusted",
        plan_text="",
        tasks=[_task()],
    )

    allowed = service._auto_execution_allowed(
        command=command,
        task=command.tasks[0],
        tool_name="workspace_write",
        arguments={"path": "safe.txt", "content": "safe"},
    )

    assert allowed is True


def test_high_risk_tool_is_never_auto_executed_in_trusted_mode(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, trusted_enabled=True)
    command = SupervisorCommand(
        id="cmd-trusted-high-risk",
        goal="Yüksek riskli trusted komut",
        status="ready",
        autonomy_mode="trusted",
        plan_text="",
        tasks=[_task()],
    )

    allowed = service._auto_execution_allowed(
        command=command,
        task=command.tasks[0],
        tool_name="safe_terminal",
        arguments={"preset": "pip_install_dev", "extra_args": []},
    )

    assert allowed is False
