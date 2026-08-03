from pathlib import Path

import pytest

from app.agent.engine import AgentEngine, _generated_source_contract_issue
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.tools.registry import build_default_tool_registry


class FileOrchestrator:
    def __init__(self):
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return OrchestrateResponse(
            answer=(
                '<<<ADAM_FILE path="src/components/Calculator.tsx">>>\n'
                'export default function Calculator() {\n'
                '  return <div>Calculator</div>;\n'
                '}\n'
                '<<<END_ADAM_FILE>>>'
            ),
            mode="auto",
            selected_route="github",
            selected_provider="github",
            model="openai/gpt-4.1-mini",
            latency_ms=1,
            task_type="coding",
            route_reason="test",
            calls_used=1,
            routing_scores=[],
        )


def test_node_test_contract_rejects_unimported_jest_globals():
    issue = _generated_source_contract_issue(
        path="tests/calculator.test.js",
        content='describe("calculator", () => {});',
        instruction=(
            "Test dosyası node:test ve node:assert/strict modüllerini "
            "açıkça import etmeli."
        ),
    )
    accepted = _generated_source_contract_issue(
        path="tests/calculator.test.js",
        content=(
            'import test from "node:test";\n'
            'import assert from "node:assert/strict";\n'
        ),
        instruction=(
            "Test dosyası node:test ve node:assert/strict modüllerini "
            "açıkça import etmeli."
        ),
    )

    assert issue is not None
    assert "node:test" in issue
    assert accepted is None


@pytest.mark.asyncio
async def test_single_file_request_uses_large_budget_and_pauses_for_write(
    tmp_path: Path,
):
    settings = Settings(workspace_root=tmp_path)
    orchestrator = FileOrchestrator()
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=build_default_tool_registry(settings=settings),
    )
    response = await engine.run(
        AgentRequest(
            message="Create calculator",
            agent_id="frontend",
            allow_deterministic_tools=False,
            additional_write_paths=[
                "src/components/Calculator.tsx"
            ],
            exclusive_write_paths=[
                "src/components/Calculator.tsx"
            ],
            response_protocol="single_file",
            single_file_path="src/components/Calculator.tsx",
            max_output_tokens=8192,
        )
    )

    assert response.status == "awaiting_approval"
    assert response.pending_approval is not None
    assert response.pending_approval.arguments["path"] == (
        "src/components/Calculator.tsx"
    )
    assert orchestrator.requests[0].max_output_tokens == 8192
    assert "JSON üretme" in orchestrator.requests[0].system_prompt
