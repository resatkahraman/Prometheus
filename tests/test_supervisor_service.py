import json
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentResponse
from app.supervisor.models import SupervisorApprovalRecord
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


PLAN = """## Doğrulanmış Proje Gerçekleri
- [file:app.py] Python dosyası mevcut.

## Varsayımlar
- Yok

## Görevler
### TASK-001 — Python birim testlerini oluştur
Seviye: zorunlu
Atanan Agent: qa
Kanıt: file:app.py
Kabul Kriterleri:
- pytest komutu exit code 0 ile tamamlanmalı.
Bağımlılıklar: yok
Bağımlılık Gerekçesi: yok
Paralel Çalışabilir: evet
Doğrulama: python -m pytest -q
Kullanıcı Onayı: gerekmez
Kesin Dosyalar: yok

## Kritik Kullanıcı Kararları
- Yok"""


class FakeAgent:
    def __init__(self):
        self.calls = []

    async def run(self, request):
        self.calls.append(request)
        if request.agent_id == "planner":
            return AgentResponse(
                answer=PLAN,
                agent_id="planner",
                agent_name="Product Planner",
                status="completed",
                steps_used=1,
                model_calls_used=1,
                tools_used=[],
                trace=[],
            )
        if request.agent_id == "qa":
            return AgentResponse(
                answer=(
                    "Test dosyası oluşturulmadı; mevcut test ortamı incelendi."
                ),
                agent_id="qa",
                agent_name="QA",
                status="completed",
                steps_used=1,
                model_calls_used=1,
                tools_used=[],
                trace=[],
            )
        return AgentResponse(
            answer=(
                "RET\nKanıt yetersiz.\nSorunlar: test dosyası yok.\n"
                "Yeniden çalışma: pytest testlerini ekle."
            ),
            agent_id="reviewer",
            agent_name="Reviewer",
            status="completed",
            steps_used=1,
            model_calls_used=1,
            tools_used=[],
            trace=[],
        )


@pytest.mark.asyncio
async def test_create_command_builds_ready_task(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def add(a,b): return a+b\n",
        encoding="utf-8",
    )
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    agents = build_default_agent_registry(tools.names())
    service = SupervisorService(
        settings=settings,
        agent=FakeAgent(),
        agents=agents,
        tools=tools,
    )

    command = await service.create(goal="Testleri ekle")
    assert command.status == "ready"
    assert command.tasks[0].status == "ready"
    assert command.execution_layers == [["TASK-001"]]


@pytest.mark.asyncio
async def test_duplicate_active_goal_reuses_existing_command(tmp_path: Path):
    (tmp_path / "app.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=FakeAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    first = await service.create(goal="Testleri ekle")
    repeated = await service.create(goal="  TESTLERİ   EKLE  ")

    assert repeated.id == first.id
    assert repeated.status == "ready"
    assert repeated.events[-1].type == "duplicate_submission_reused"
    assert len(await service.store.list()) == 1


@pytest.mark.asyncio
async def test_force_new_allows_repeating_the_same_goal(tmp_path: Path):
    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path, supervisor_persistence_enabled=False)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=FakeAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    first = await service.create(goal="Aynı görevi çalıştır")
    second = await service.create(goal="Aynı görevi çalıştır", force_new=True)

    assert second.id != first.id
    assert len(await service.list()) == 2


@pytest.mark.asyncio
async def test_archive_hides_command_and_releases_duplicate_goal(tmp_path: Path):
    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path, supervisor_persistence_enabled=False)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=FakeAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    first = await service.create(goal="Tekrar kullanılabilir görev")
    archived = await service.archive(first.id)
    repeated = await service.create(goal="Tekrar kullanılabilir görev")

    assert archived.archived is True
    assert archived.archived_at is not None
    assert first.id not in {item.id for item in await service.list()}
    assert repeated.id != first.id


@pytest.mark.asyncio
async def test_delete_removes_command_metadata(tmp_path: Path):
    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path, supervisor_persistence_enabled=False)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=FakeAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    command = await service.create(goal="Silinecek görev")
    assert await service.delete(command.id) is True
    with pytest.raises(KeyError):
        await service.get(command.id)


@pytest.mark.asyncio
async def test_duplicate_goal_retires_unsafe_pending_output_and_replans(tmp_path: Path):
    (tmp_path / "app.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=FakeAgent(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    first = await service.create(goal="Aynı hesap makinesi")
    task = first.tasks[0]
    task.title = "Calculator için tek dosya statik web uygulaması"
    task.status = "awaiting_approval"
    task.approval_id = "approval-1"
    task.approval_state = "pending"
    task.approval_phase = "worker"
    task.agent_session_id = "session-1"
    task.approval_history.append(
        SupervisorApprovalRecord(
            version=1,
            approval_id="approval-1",
            state="pending",
            phase="worker",
            tool="workspace_write",
            arguments={
                "path": "calculator.html",
                "content": "<button>C</button><button>DEL</button>+-*/.=<script>eval(x)</script>",
            },
        )
    )
    first.status = "awaiting_approval"
    await service.store.put(first)

    repeated = await service.create(goal="Aynı hesap makinesi")
    retired = await service.store.get(first.id)

    assert repeated.id != first.id
    assert retired.tasks[0].status == "rework_required"
    assert retired.tasks[0].approval_state == "rejected"
    assert retired.tasks[0].approval_history[-1].state == "rejected"


@pytest.mark.asyncio
async def test_reviewer_rejection_marks_rework(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def add(a,b): return a+b\n",
        encoding="utf-8",
    )
    settings = Settings(
        workspace_root=tmp_path,
        supervisor_auto_review=True,
    )
    tools = build_default_tool_registry(settings=settings)
    agents = build_default_agent_registry(tools.names())
    service = SupervisorService(
        settings=settings,
        agent=FakeAgent(),
        agents=agents,
        tools=tools,
    )

    command = await service.create(goal="Testleri ekle")
    command.tasks[0].exact_files = []
    command.tasks[0].assigned_agent = "qa"
    await service.store.put(command)
    command = await service.run_task(
        command_id=command.id,
        task_id="TASK-001",
    )
    assert command.tasks[0].status == "rework_required"
    assert any(
        handoff.type == "review_reject"
        for handoff in command.handoffs
    )
