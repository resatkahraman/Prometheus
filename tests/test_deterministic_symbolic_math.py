import pytest

from app.agent.engine import AgentEngine
from app.core.config import Settings
from app.core.schemas import AgentRequest
from app.tools.registry import build_default_tool_registry


class ForbiddenOrchestrator:
    async def run(self, request):
        raise AssertionError("Açık symbolic_math isteğinde model çağrılmamalı.")


@pytest.mark.asyncio
async def test_calculation_derivative_uses_zero_model_calls():
    settings = Settings(
        agent_max_steps=6,
        agent_max_model_calls=5,
    )
    engine = AgentEngine(
        settings=settings,
        orchestrator=ForbiddenOrchestrator(),
        tools=build_default_tool_registry(settings=settings),
    )

    result = await engine.run(
        AgentRequest(
            message=(
                "x**3 + 2*x**2 - x ifadesinin "
                "x'e göre türevini hesapla."
            ),
            agent_id="calculation",
        )
    )

    assert result.status == "completed"
    assert result.model_calls_used == 0
    assert result.final_route == "deterministic"
    assert result.final_model == "sympy"
    assert result.answer == "Türev: 3*x**2 + 4*x - 1"
    assert result.trace[0].tool == "symbolic_math"
