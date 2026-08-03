from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.agent.protocol import parse_agent_action
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.memory.attention import AttentionBroker, AttentionCard
from app.memory.project import ProjectMemoryStore
from app.tools.registry import build_default_tool_registry


class ExpandingFileOrchestrator:
    def __init__(self) -> None:
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            answer = (
                '{"action":"need_context","reason":"add sembolü gerekli.",'
                '"paths":[],"symbols":["add"]}'
            )
        else:
            answer = (
                '<<<ADAM_FILE path="src/result.js">>>\n'
                "import { add } from './helper.js';\n"
                "export const result = add(2, 3);\n"
                "<<<END_ADAM_FILE>>>"
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


class RepairingFileOrchestrator:
    def __init__(self) -> None:
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        call = len(self.requests)
        if call == 1:
            answer = (
                '{"action":"need_context","reason":"contract needed",'
                '"paths":[],"symbols":["applyEncodedOperation"]}'
            )
        elif call == 2:
            answer = (
                '<<<ADAM_FILE path="src/use_contract.js">>>\n'
                "import { applyEncodedOperation, inventedOperator } "
                "from './math_contract.js';\n"
                "export const value = "
                "applyEncodedOperation(2, 3, inventedOperator);\n"
                "<<<END_ADAM_FILE>>>"
            )
        else:
            answer = (
                '<<<ADAM_FILE path="src/use_contract.js">>>\n'
                "import { applyEncodedOperation } "
                "from './math_contract.js';\n"
                "export const value = "
                "applyEncodedOperation(2, 3, 'plus_v7');\n"
                "<<<END_ADAM_FILE>>>"
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


def test_need_context_protocol_is_explicit_and_bounded():
    action = parse_agent_action(
        '{"action":"need_context","reason":"missing symbol",'
        '"paths":["src/a.js"],"symbols":["calculate"]}'
    )
    assert action.action == "need_context"
    assert action.arguments == {
        "paths": ["src/a.js"],
        "symbols": ["calculate"],
    }


@pytest.mark.asyncio
async def test_symbol_dependency_index_and_hash_invalidation(
    tmp_path: Path,
):
    store = ProjectMemoryStore(tmp_path / "memory.db")
    await store.remember_file(
        path="src/calculator.js",
        content="export function calculate(a, b) { return a + b; }\n",
    )
    await store.remember_file(
        path="src/app.js",
        content=(
            "import { calculate } from './calculator.js';\n"
            "export const result = calculate(2, 3);\n"
        ),
    )

    assert await store.resolve_symbols(["calculate"]) == [
        "src/calculator.js"
    ]
    assert await store.related_paths("src/app.js") == [
        "src/calculator.js"
    ]

    await store.remember_file(
        path="src/calculator.js",
        content="export function sum(a, b) { return a + b; }\n",
    )
    cards = await store.context_cards(
        paths=["src/calculator.js"],
    )
    assert await store.resolve_symbols(["calculate"]) == []
    assert not any("defines function calculate" in card.claim for card in cards)
    assert any("defines function sum" in card.claim for card in cards)


@pytest.mark.asyncio
async def test_local_import_must_exist_in_verified_symbol_index(
    tmp_path: Path,
):
    store = ProjectMemoryStore(tmp_path / "memory.db")
    await store.remember_file(
        path="src/math_contract.js",
        content=(
            "export function applyEncodedOperation(a, b, operator) "
            "{ return operator === 'plus_v7' ? a + b : a - b; }\n"
        ),
    )
    validation = await store.validate_source_evidence(
        path="src/use_contract.js",
        content=(
            "import { applyEncodedOperation, inventedOperator } "
            "from './math_contract.js';\n"
        ),
    )
    assert validation["valid"] is False
    assert "inventedOperator" in validation["issues"][0]
    assert "applyEncodedOperation" in validation["issues"][0]


@pytest.mark.asyncio
async def test_planned_future_import_is_pending_but_not_hallucinated(
    tmp_path: Path,
):
    store = ProjectMemoryStore(tmp_path / "memory.db")
    validation = await store.validate_source_evidence(
        path="src/app.js",
        content=(
            "import { calculate } from './calculator.js';\n"
            "export const result = calculate(2, 3, 'add');\n"
        ),
        allowed_missing_paths=["src/calculator.js"],
    )

    assert validation["valid"] is True
    assert validation["missing_context_paths"] == []
    assert validation["pending_imports"] == [
        {
            "name": "calculate",
            "reference": "./calculator.js",
            "resolved_path": "src/calculator.js",
        }
    ]

    await store.remember_file(
        path="src/calculator.js",
        content="export function sum(a, b) { return a + b; }\n",
    )
    existing_validation = await store.validate_source_evidence(
        path="src/app.js",
        content="import { calculate } from './calculator.js';\n",
        allowed_missing_paths=["src/calculator.js"],
    )
    assert existing_validation["valid"] is False
    assert "calculate" in existing_validation["issues"][0]


@pytest.mark.asyncio
async def test_hypothesis_cannot_become_fact_without_runtime_evidence(
    tmp_path: Path,
):
    store = ProjectMemoryStore(tmp_path / "memory.db")
    await store.remember_file(
        path="src/app.js",
        content="export const value = 1;\n",
    )
    hypothesis = await store.add_hypothesis(
        claim="A history panel improves the calculator.",
        rationale="Users may want to inspect previous operations.",
        task_scope="calculator-ui",
    )
    creative_cards = await store.context_cards(
        paths=["src/app.js"],
        include_hypotheses=True,
    )
    file_card = next(
        card for card in creative_cards if card.evidence_type == "file"
    )
    assert any(card.state == "hypothesis" for card in creative_cards)

    with pytest.raises(ValueError, match="test, tool or user-decision"):
        await store.promote_hypothesis(
            hypothesis_id=hypothesis.id,
            evidence_ids=[file_card.id],
        )

    test_evidence = await store.record_evidence(
        claim="History panel acceptance test passed.",
        evidence_type="test",
        evidence_ref="npm test -- history: exit 0",
    )
    promoted = await store.promote_hypothesis(
        hypothesis_id=hypothesis.id,
        evidence_ids=[test_evidence],
    )
    verified_cards = await store.context_cards(
        paths=["src/app.js"],
        include_hypotheses=False,
    )
    assert promoted.status == "promoted"
    assert any(
        card.claim == "A history panel improves the calculator."
        and card.state == "verified"
        for card in verified_cards
    )


def test_attention_broker_labels_hypotheses_and_respects_budget():
    broker = AttentionBroker()
    cards = [
        AttentionCard(
            id="verified-target",
            claim="src/calculator.js defines calculate.",
            source_path="src/calculator.js",
            evidence_type="symbol",
            state="verified",
            confidence=1.0,
        ),
        AttentionCard(
            id="idea",
            claim="Add a scientific mode.",
            source_path=None,
            evidence_type="hypothesis",
            state="hypothesis",
            confidence=0.25,
        ),
    ]
    capsule = broker.build_capsule(
        task_text="Update calculate in calculator.js",
        target_path="src/calculator.js",
        cards=cards,
        max_chars=500,
    )
    assert capsule.chars <= 500
    assert "[VERIFIED]" in capsule.text
    assert "[HYPOTHESIS]" in capsule.text
    assert capsule.selected_card_ids[0] == "verified-target"


@pytest.mark.asyncio
async def test_single_file_agent_expands_only_requested_symbol_context(
    tmp_path: Path,
):
    helper = tmp_path / "src" / "helper.js"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        "export function add(a, b) { return a + b; }\n",
        encoding="utf-8",
    )
    settings = Settings(
        workspace_root=tmp_path,
        project_memory_database_path=Path(".adam/memory.db"),
        agent_context_expansion_max_requests=2,
        agent_context_expansion_max_files=2,
    )
    orchestrator = ExpandingFileOrchestrator()
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=build_default_tool_registry(settings=settings),
    )
    await engine.project_memory.remember_file(
        path="src/helper.js",
        content=helper.read_text(encoding="utf-8"),
    )

    response = await engine.run(
        AgentRequest(
            message="Create src/result.js using add.",
            agent_id="frontend",
            allow_deterministic_tools=False,
            disable_auto_context=True,
            exclusive_write_paths=["src/result.js"],
            response_protocol="single_file",
            single_file_path="src/result.js",
            max_output_tokens=2_000,
        )
    )

    assert response.status == "awaiting_approval"
    assert len(orchestrator.requests) == 2
    assert response.trace[0].action == "context"
    assert response.trace[0].tool == "adaptive_context"
    second_prompt = "\n".join(
        message.content for message in orchestrator.requests[1].messages
    )
    assert "src/helper.js" in second_prompt
    assert "function add" in second_prompt
    assert "CONTEXT_EXPANSION_APPLIED" in second_prompt


@pytest.mark.asyncio
async def test_evidence_gate_rejects_hallucinated_import_before_write(
    tmp_path: Path,
):
    contract = tmp_path / "src" / "math_contract.js"
    contract.parent.mkdir(parents=True)
    contract.write_text(
        "export function applyEncodedOperation(a, b, operator) {\n"
        "  return operator === 'plus_v7' ? a + b : a - b;\n"
        "}\n",
        encoding="utf-8",
    )
    settings = Settings(
        workspace_root=tmp_path,
        project_memory_database_path=Path(".adam/memory.db"),
    )
    orchestrator = RepairingFileOrchestrator()
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=build_default_tool_registry(settings=settings),
    )
    await engine.project_memory.remember_file(
        path="src/math_contract.js",
        content=contract.read_text(encoding="utf-8"),
    )

    response = await engine.run(
        AgentRequest(
            message="Create src/use_contract.js without guessing imports.",
            agent_id="frontend",
            allow_deterministic_tools=False,
            disable_auto_context=True,
            exclusive_write_paths=["src/use_contract.js"],
            response_protocol="single_file",
            single_file_path="src/use_contract.js",
            max_steps=5,
            max_model_calls=5,
            supervised_budget=True,
        )
    )

    assert response.status == "awaiting_approval"
    assert [step.action for step in response.trace] == [
        "context",
        "evidence_rejected",
        "approval_required",
    ]
    assert response.pending_approval.arguments["content"].endswith(
        "applyEncodedOperation(2, 3, 'plus_v7');\n"
    )
    assert not (tmp_path / "src" / "use_contract.js").exists()
