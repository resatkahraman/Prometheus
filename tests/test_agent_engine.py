import pytest

from app.agent.engine import AgentEngine
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.tools.registry import build_default_tool_registry


class FakeOrchestrator:
    def __init__(self):
        self.calls = 0

    async def run(self, request):
        self.calls += 1
        if self.calls == 1:
            answer = (
                '{"action":"tool","reason":"Hesap gerekli.",'
                '"tool":"calculator","arguments":{"expression":"2+3"}}'
            )
        else:
            answer = (
                '{"action":"final","reason":"Araç sonucu alındı.",'
                '"answer":"Sonuç 5."}'
            )
        return OrchestrateResponse(
            answer=answer,
            mode="auto",
            selected_route="groq_fast",
            selected_provider="groq",
            model="llama-test",
            latency_ms=10,
            task_type="general",
            route_reason="test",
            calls_used=1,
            routing_scores=[],
        )


@pytest.mark.asyncio
async def test_agent_executes_tool_then_finishes():
    engine = AgentEngine(
        settings=Settings(agent_max_steps=4, agent_max_model_calls=6),
        orchestrator=FakeOrchestrator(),
        tools=build_default_tool_registry(),
    )
    result = await engine.run(
        AgentRequest(message="2+3 kaçtır?", include_trace=True)
    )
    assert result.status == "completed"
    assert result.answer == "Sonuç 5."
    assert result.tools_used == ["calculator"]
    assert result.steps_used == 2
    assert result.trace[0].tool_result["result"] == 5
