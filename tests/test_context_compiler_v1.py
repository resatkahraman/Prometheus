import json
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.memory.context_compiler import ContextCompiler, ContextSegment
from app.memory.project import ProjectMemoryStore
from app.supervisor.models import SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoModel:
    async def run(self, request):
        raise AssertionError("Shadow context compilation must not call a model.")


def test_context_compiler_deduplicates_and_preserves_required_source():
    compiler = ContextCompiler()
    compilation = compiler.compile(
        task_text="Update calculate without changing its contract.",
        max_chars=1_000,
        baseline_chars=1_400,
        segments=[
            ContextSegment(
                id="target",
                layer="L2",
                text="export const calculate = (a, b) => a + b;",
                priority=100,
                required=True,
                source_path="src/calculate.js",
                source_sha256="abc123",
            ),
            ContextSegment(
                id="duplicate-outline",
                layer="L3",
                text="export const calculate = (a, b) => a + b;",
                priority=20,
            ),
            ContextSegment(
                id="evidence",
                layer="L1",
                text="[VERIFIED] calculate accepts two arguments.",
                priority=80,
            ),
        ],
    )

    assert compilation.eligible is True
    assert compilation.fallback_required is False
    assert compilation.chars <= 1_000
    assert compilation.saved_chars > 0
    assert "target" in compilation.selected_segment_ids
    assert "duplicate-outline" in compilation.deduplicated_segment_ids
    assert compilation.source_hashes == {
        "src/calculate.js": "abc123"
    }


def test_context_compiler_rejects_savings_that_clip_required_evidence():
    compilation = ContextCompiler().compile(
        task_text="Preserve the complete contract.",
        max_chars=250,
        segments=[
            ContextSegment(
                id="large-contract",
                layer="L2",
                text="contract-line\n" * 200,
                priority=100,
                required=True,
            )
        ],
    )

    assert compilation.chars <= 250
    assert compilation.fallback_required is True
    assert compilation.eligible is False
    assert "CONTEXT_COMPILER_REQUIRED_FALLBACK" in compilation.text


@pytest.mark.asyncio
async def test_local_rag_uses_verified_cards_and_drops_stale_symbols(
    tmp_path: Path,
):
    store = ProjectMemoryStore(tmp_path / "memory.db")
    await store.remember_file(
        path="src/pricing.js",
        content="export function calculatePrice() { return 90; }\n",
    )
    await store.remember_file(
        path="src/unrelated.js",
        content="export function renderTheme() { return 'dark'; }\n",
    )

    first = await store.retrieve_context_cards(
        query="calculatePrice pricing total",
        seed_paths=["src/pricing.js"],
        limit=10,
    )
    assert any("calculatePrice" in card.claim for card in first)

    await store.remember_file(
        path="src/pricing.js",
        content="export function computeTotal() { return 90; }\n",
    )
    second = await store.retrieve_context_cards(
        query="pricing total",
        seed_paths=["src/pricing.js"],
        limit=10,
    )
    assert not any("calculatePrice" in card.claim for card in second)
    assert any("computeTotal" in card.claim for card in second)


@pytest.mark.asyncio
async def test_supervisor_shadow_mode_records_safe_cache_telemetry(
    tmp_path: Path,
):
    files = {
        "src/pricing.js": (
            "export function calculatePrice(quantity) {\n"
            "  return quantity * 30;\n"
            "}\n"
        ),
        "test/pricing.contract.test.js": (
            "import { calculatePrice } from '../src/pricing.js';\n"
            "if (calculatePrice(3) !== 90) throw new Error('contract');\n"
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
        context_compiler_shadow_budget_chars=2_500,
        supervisor_focused_related_full_files=1,
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
        title="Preserve pricing contract",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["calculatePrice(3) returns 90"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayÄ±r",
        verification="node --test test/pricing.contract.test.js",
        user_approval="gerekli",
        exact_files=["src/pricing.js"],
    )

    first_context = await service._focused_context(
        task,
        target_path="src/pricing.js",
    )
    second_context = await service._focused_context(
        task,
        target_path="src/pricing.js",
    )
    telemetry = (
        await service.project_memory.latest_context_compilation(
            "supervisor_focused"
        )
    )

    assert "calculatePrice" in first_context
    assert telemetry is not None
    assert telemetry["mode"] == "shadow"
    assert telemetry["cache_hit"] == 1
    assert telemetry["baseline_chars"] == len(second_context)
    assert telemetry["candidate_chars"] <= 2_500
    assert telemetry["eligible"] == 1
    # The contract is already present as a full source segment, so RAG must
    # not repeat its symbol/dependency cards.
    assert json.loads(telemetry["retrieved_card_ids_json"]) == []
    assert json.loads(telemetry["missing_evidence_json"]) == []
    previous_hashes = json.loads(telemetry["source_hashes_json"])

    (tmp_path / "src" / "pricing.js").write_text(
        "export function calculatePrice(quantity) {\n"
        "  return quantity * 31;\n"
        "}\n",
        encoding="utf-8",
    )
    await service._focused_context(task, target_path="src/pricing.js")
    invalidated = (
        await service.project_memory.latest_context_compilation(
            "supervisor_focused"
        )
    )
    summary = await service.project_memory.context_compiler_summary()
    assert invalidated["cache_hit"] == 0
    assert json.loads(invalidated["source_hashes_json"]) != previous_hashes
    assert summary["runs"] == 3
    assert summary["cache_hits"] == 1
    assert summary["eligible_runs"] == 3
    assert (
        summary["beneficial_runs"] + summary["bypassed_runs"]
        == summary["runs"]
    )

    raw_database = (
        tmp_path / ".adam" / "memory.db"
    ).read_bytes()
    assert b"quantity * 30" not in raw_database


@pytest.mark.asyncio
async def test_active_mode_keeps_target_import_and_verification_contract(
    tmp_path: Path,
):
    files = {
        "src/pricing.js": (
            "export function calculatePrice(quantity) {\n"
            "  return quantity * 30;\n"
            "}\n"
        ),
        "src/view-model.js": (
            "import { calculatePrice } from './pricing.js';\n"
            "export const summary = (quantity) => "
            "`${calculatePrice(quantity)} TL`;\n"
        ),
        "test/view-model.contract.test.js": (
            "import { summary } from '../src/view-model.js';\n"
            "if (summary(3) !== '90 TL') throw new Error('contract');\n"
        ),
        "README.md": "An unrelated project description.\n" * 20,
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    settings = Settings(
        workspace_root=tmp_path,
        project_memory_database_path=Path(".adam/memory.db"),
        context_compiler_mode="active",
        supervisor_focused_context_max_chars=5_000,
        supervisor_focused_related_full_files=1,
    )
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoModel(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = SupervisorTask(
        id="TASK-002",
        title="Build the view model",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["summary(3) returns 90 TL"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayÄ±r",
        verification="node --test test/view-model.contract.test.js",
        user_approval="gerekli",
        exact_files=["src/view-model.js", "README.md"],
    )

    context = await service._focused_context(
        task,
        target_path="src/view-model.js",
    )
    telemetry = (
        await service.project_memory.latest_context_compilation(
            "supervisor_focused"
        )
    )

    assert context.startswith("ADAM_CTX_V1")
    assert "return quantity * 30" in context
    assert "summary(3) !== '90 TL'" in context
    assert telemetry["mode"] == "active"
    assert telemetry["eligible"] == 1
    assert telemetry["candidate_chars"] < telemetry["baseline_chars"]


@pytest.mark.asyncio
async def test_active_mode_falls_back_when_verification_evidence_is_missing(
    tmp_path: Path,
):
    target = tmp_path / "src" / "pricing.js"
    target.parent.mkdir(parents=True)
    target.write_text(
        "export const total = () => 90;\n",
        encoding="utf-8",
    )
    settings = Settings(
        workspace_root=tmp_path,
        project_memory_database_path=Path(".adam/memory.db"),
        context_compiler_mode="active",
        supervisor_focused_context_max_chars=3_000,
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
        title="Preserve the missing external contract",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["Contract passes"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayÄ±r",
        verification="node --test test/missing.contract.test.js",
        user_approval="gerekli",
        exact_files=["src/pricing.js"],
    )

    context = await service._focused_context(
        task,
        target_path="src/pricing.js",
    )
    telemetry = (
        await service.project_memory.latest_context_compilation(
            "supervisor_focused"
        )
    )

    assert context.startswith("PROJECT_MEMORY_V2")
    assert telemetry["fallback_required"] == 1
    assert telemetry["eligible"] == 0
    assert json.loads(telemetry["missing_evidence_json"]) == [
        "test/missing.contract.test.js"
    ]
