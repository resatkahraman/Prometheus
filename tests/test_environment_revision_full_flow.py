from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.models import (
    SupervisorApprovalRecord,
    SupervisorCommand,
    SupervisorTask,
)
from app.supervisor.service import SupervisorService
from app.tools.fingerprint import tool_fingerprint
from app.tools.registry import build_default_tool_registry


class NoModelAgent:
    async def run(self, request):
        raise AssertionError("No model call expected")


@pytest.mark.asyncio
async def test_persisted_node_install_allows_npm_test_retry(
    monkeypatch,
    tmp_path: Path,
):
    component = tmp_path / "src/components/ScoreCard.tsx"
    test_file = tmp_path / "src/components/ScoreCard.test.tsx"
    component.parent.mkdir(parents=True)
    component.write_text(
        "export default function ScoreCard(){return null}",
        encoding="utf-8",
    )
    test_file.write_text("import { test } from 'vitest'; test('x',()=>{})", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest --run"}}',
        encoding="utf-8",
    )
    vitest = tmp_path / "node_modules" / ".bin" / "vitest"
    vitest.parent.mkdir(parents=True)
    vitest.write_text("", encoding="utf-8")

    settings = Settings(
        workspace_root=tmp_path,
        supervisor_approval_background=False,
    )
    tools = build_default_tool_registry(settings=settings)
    terminal = tools.get("safe_terminal")
    monkeypatch.setattr(
        terminal,
        "_resolve_npm_base",
        lambda: ["node", "npm-cli.js"],
    )
    calls = []

    async def fake_direct(name, arguments):
        calls.append((name, arguments))
        assert name == "safe_terminal"
        assert arguments["preset"] == "npm_test"
        return {
            "preset": "npm_test",
            "command": ["npm", "test", "--", "--run"],
            "logical_command": ["npm", "test", "--", "--run"],
            "cwd": str(tmp_path),
            "exit_code": 0,
            "timed_out": False,
            "stdout": "4 passed",
            "stderr": "",
            "success": True,
        }

    monkeypatch.setattr(tools, "execute_direct", fake_direct)

    failed_args = {
        "preset": "npm_test",
        "extra_args": ["--run"],
    }
    install_args = {
        "preset": "install_node_lts",
        "extra_args": [],
    }
    task = SupervisorTask(
        id="TASK-002",
        title="ScoreCard",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["npm test başarılı"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test -- --run",
        user_approval="gerekli",
        exact_files=[
            "src/components/ScoreCard.tsx",
            "src/components/ScoreCard.test.tsx",
        ],
        status="rework_required",
        autonomy_granted=True,
        recovery_reason="repeated_failure_blocked",
        blocked_reason="old npm missing",
        approval_version=2,
        approval_history=[
            SupervisorApprovalRecord(
                version=1,
                approval_id="failed",
                state="applied",
                phase="worker",
                tool="safe_terminal",
                arguments=failed_args,
                fingerprint=tool_fingerprint(
                    "safe_terminal",
                    failed_args,
                ),
                success=False,
                result={
                    "preset": "npm_test",
                    "exit_code": 127,
                    "success": False,
                    "failure_kind": "missing_command",
                    "missing_command": "npm",
                },
            ),
            SupervisorApprovalRecord(
                version=2,
                approval_id="install",
                state="applied",
                phase="worker",
                tool="safe_terminal",
                arguments=install_args,
                fingerprint=tool_fingerprint(
                    "safe_terminal",
                    install_args,
                ),
                success=True,
                result={
                    "preset": "install_node_lts",
                    "exit_code": 0,
                    "success": True,
                    "npm_available_after_install": True,
                },
            ),
        ],
    )
    command = SupervisorCommand(
        id="cmd",
        goal="ScoreCard testleri",
        status="ready",
        autonomy_mode="task",
        plan_text="",
        tasks=[task],
    )

    service = SupervisorService(
        settings=settings,
        agent=NoModelAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    await service.store.put(command)

    result = await service._advance_structured_task(
        command_id="cmd",
        task_id="TASK-002",
        reason="resume_after_upgrade",
    )

    assert calls == [
        (
            "safe_terminal",
            {
                "preset": "npm_test",
                "extra_args": ["--run"],
            },
        )
    ]
    assert result.tasks[0].status == "completed"
    assert result.tasks[0].environment_revision == 1
    assert any(
        event.type == "environment_revision_advanced"
        for event in result.events
    )
    assert not any(
        event.type == "duplicate_verification_blocked"
        for event in result.events
    )
