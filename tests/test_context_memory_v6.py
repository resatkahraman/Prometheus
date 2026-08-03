from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.agents.registry import build_default_agent_registry
from app.approvals.manager import ApprovalManager
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.memory.project import ProjectMemoryStore
from app.supervisor.models import SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class ContextOrchestrator:
    def __init__(self) -> None:
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return OrchestrateResponse(
            answer=(
                '{"action":"final","reason":"İnceleme tamamlandı.",'
                '"answer":"Mevcut durum: Python projesi tek app.py dosyasıdır '
                've hesaplama davranışı bu giriş noktasında toplanmıştır.\\n'
                'Mimari yapı: Tek modüllü yapı iş mantığı ile giriş katmanını '
                'birbirine bağlamaktadır.\\n'
                'Riskler: Test kapsamı ve açık katman sınırları eksiktir.\\n'
                'Önerilen hedef mimari: İş mantığı core modülüne, testler tests '
                'modülüne ayrılmalıdır.\\n'
                'Geçiş ve doğrulama planı: Önce davranış testleri yazılmalı, '
                'sonra modüller ayrılmalı ve pytest çalıştırılmalıdır."}'
            ),
            mode="auto",
            selected_route="gemini",
            selected_provider="gemini",
            model="test",
            latency_ms=1,
            task_type="reasoning",
            route_reason="test",
            calls_used=1,
            routing_scores=[],
        )


class LargeWriteOrchestrator:
    def __init__(self) -> None:
        self.requests = []
        self.calls = 0

    async def run(self, request):
        self.requests.append(request)
        self.calls += 1
        if self.calls == 1:
            content = "PAYLOAD_MARKER-" * 700
            answer = (
                '{"action":"tool","reason":"Dosyayı oluştur.",'
                '"tool":"workspace_write","arguments":'
                f'{{"path":"large.txt","content":"{content}"}}}}'
            )
        else:
            answer = (
                '{"action":"final","reason":"Dosya oluşturuldu.",'
                '"answer":"large.txt oluşturuldu. Değişen dosya: large.txt.\\n'
                'Doğrulama Durumu: Metin dosyası yazma aracı başarıyla '
                'tamamlandı; test edilmedi ve çalıştırılabilir test gerekmiyor."}'
            )
        return OrchestrateResponse(
            answer=answer,
            mode="auto",
            selected_route="github",
            selected_provider="github",
            model="test",
            latency_ms=1,
            task_type="coding",
            route_reason="test",
            calls_used=1,
            routing_scores=[],
        )


class NoModel:
    async def run(self, request):
        raise AssertionError("model should not run")


@pytest.mark.asyncio
async def test_project_memory_tracks_hashes_without_full_source(tmp_path: Path):
    store = ProjectMemoryStore(tmp_path / ".adam" / "memory.db")
    source = (
        "def calculate(value):\n"
        '    return "BODY_SECRET_THAT_MUST_NOT_BE_STORED" + value\n'
    )

    first = await store.remember_file(path="app.py", content=source)
    second = await store.remember_file(path="app.py", content=source)
    changed = await store.remember_file(
        path="app.py",
        content=source + "\nclass Calculator:\n    pass\n",
    )

    assert first.state == "new"
    assert second.state == "unchanged"
    assert changed.state == "changed"
    assert "def calculate" in changed.outline
    assert "BODY_SECRET_THAT_MUST_NOT_BE_STORED" not in changed.outline


@pytest.mark.asyncio
async def test_unchanged_bootstrap_file_uses_outline_on_next_run(
    tmp_path: Path,
):
    (tmp_path / "app.py").write_text(
        "def calculate(value):\n"
        '    return "FULL_BODY_SHOULD_NOT_REPEAT" + value\n',
        encoding="utf-8",
    )
    settings = Settings(
        workspace_root=tmp_path,
        project_memory_database_path=Path(".adam/memory.db"),
    )
    orchestrator = ContextOrchestrator()
    tools = build_default_tool_registry(settings=settings)
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=tools,
    )

    request = AgentRequest(
        message="Projeyi incele ve mimarisini açıkla.",
        agent_id="architect",
        usage_scope="mission-123",
        usage_task_id="TASK-001",
    )
    await engine.run(request)
    await engine.run(request)

    first_prompt = "\n".join(
        message.content for message in orchestrator.requests[0].messages
    )
    second_prompt = "\n".join(
        message.content for message in orchestrator.requests[1].messages
    )
    assert "FULL_BODY_SHOULD_NOT_REPEAT" in first_prompt
    assert "FULL_BODY_SHOULD_NOT_REPEAT" not in second_prompt
    assert '"content_mode": "outline"' in second_prompt
    assert "def calculate" in second_prompt
    assert orchestrator.requests[1].usage_scope == "mission-123"
    assert orchestrator.requests[1].usage_task_id == "TASK-001"


@pytest.mark.asyncio
async def test_applied_large_write_is_replaced_by_small_receipt(
    tmp_path: Path,
):
    settings = Settings(
        workspace_root=tmp_path,
        project_memory_enabled=False,
        agent_context_max_chars=6_000,
        agent_context_base_max_chars=2_000,
        agent_context_memory_max_chars=800,
        agent_tool_content_max_chars=1_000,
    )
    orchestrator = LargeWriteOrchestrator()
    registry = build_default_tool_registry(
        settings=settings,
        approvals=ApprovalManager(ttl_seconds=300),
    )
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=registry,
    )

    first = await engine.run(
        AgentRequest(message="large.txt oluştur")
    )
    second = await engine.approve(
        session_id=first.session_id,
        approval_id=first.pending_approval.id,
    )

    assert second.status == "completed"
    followup_prompt = "\n".join(
        message.content for message in orchestrator.requests[1].messages
    )
    assert "PAYLOAD_MARKER" not in followup_prompt
    assert "content_receipt" in followup_prompt
    assert "SESSION_MEMORY" in followup_prompt
    assert sum(
        len(message.content)
        for message in orchestrator.requests[1].messages
    ) <= settings.agent_context_max_chars


@pytest.mark.asyncio
async def test_focused_context_sends_related_files_and_outlines_rest(
    tmp_path: Path,
):
    files = {
        "package.json": '{"name":"calc","scripts":{"test":"node --test"}}',
        "index.html": (
            "<title>Calculator</title>\n"
            "<!-- UNRELATED_INDEX_BODY_MUST_NOT_BE_FULL -->"
        ),
        "styles.css": ".calculator { display: grid; }",
        "src/app.js": "import { calculate } from './calculator.js';",
        "src/calculator.js": (
            "export function calculate(a, b) { return a + b; }"
        ),
        "tests/calculator.test.js": (
            "import { calculate } from '../src/calculator.js';"
        ),
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    settings = Settings(
        workspace_root=tmp_path,
        project_memory_database_path=Path(".adam/memory.db"),
        context_compiler_mode="shadow",
        supervisor_focused_context_max_chars=4_000,
        supervisor_focused_related_full_files=2,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoModel(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="Calculator frontend",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["Arithmetic tests pass"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test",
        user_approval="gerekli",
        exact_files=list(files),
    )

    context = await service._focused_context(
        task,
        target_path="tests/calculator.test.js",
    )
    stats = await service.project_memory.latest_context(
        "supervisor_focused"
    )

    assert "HEDEF: tests/calculator.test.js" in context
    assert "İLGİLİ: src/calculator.js" in context
    assert "İLGİLİ: package.json" in context
    assert "DİĞER KESİN DOSYALAR" in context
    assert "UNRELATED_INDEX_BODY_MUST_NOT_BE_FULL" not in context
    assert len(context) <= settings.supervisor_focused_context_max_chars
    assert stats["full_file_count"] == 3
    assert stats["summarized_file_count"] == 3


@pytest.mark.asyncio
async def test_focused_context_includes_verification_contract_and_import(
    tmp_path: Path,
):
    files = {
        "package.json": '{"scripts":{"test":"node --test"}}',
        "src/pricing.js": "export const total = () => 90;",
        "src/view-model.js": (
            'import { total } from "./pricing.js";\n'
            "export const summary = () => total();"
        ),
        "test/view-model.contract.test.js": (
            'import { summary } from "../src/view-model.js";\n'
            "if (summary() !== 90) throw new Error('contract');"
        ),
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    settings = Settings(
        workspace_root=tmp_path,
        project_memory_database_path=Path(".adam/memory.db"),
        context_compiler_mode="shadow",
        supervisor_focused_context_max_chars=5_000,
        supervisor_focused_related_full_files=2,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoModel(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="View model",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["Contract test passes"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification=(
            "npm test -- test/view-model.contract.test.js"
        ),
        user_approval="gerekli",
        exact_files=["src/view-model.js"],
    )

    context = await service._focused_context(
        task,
        target_path="src/view-model.js",
    )

    assert "HEDEF: src/view-model.js" in context
    assert "İLGİLİ: src/pricing.js" in context
    assert "İLGİLİ: test/view-model.contract.test.js" in context
    assert "summary() !== 90" in context


@pytest.mark.asyncio
async def test_focused_context_includes_read_only_plan_evidence(
    tmp_path: Path,
):
    files = {
        "src/pricing.js": "export const total = () => 90;",
        "src/view-model.js": (
            "export const summary = () => "
            "({ itemCount: 3, total: 90 });"
        ),
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    settings = Settings(
        workspace_root=tmp_path,
        project_memory_database_path=Path(".adam/memory.db"),
        context_compiler_mode="shadow",
        supervisor_focused_context_max_chars=5_000,
        supervisor_focused_related_full_files=2,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoModel(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-001",
        title="Node edge tests",
        priority="zorunlu",
        assigned_agent="qa",
        evidence=[
            {"type": "file", "value": "src/pricing.js"},
            {"type": "file", "value": "src/view-model.js"},
        ],
        acceptance_criteria=["Node edge cases are tested"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test",
        user_approval="gerekli",
        exact_files=["test/edge-cases.test.js"],
    )

    context = await service._focused_context(
        task,
        target_path="test/edge-cases.test.js",
    )

    assert "HEDEF: test/edge-cases.test.js" in context
    assert "İLGİLİ: src/pricing.js" in context
    assert "İLGİLİ: src/view-model.js" in context
    assert "itemCount: 3" in context
