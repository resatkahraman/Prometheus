from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.tools.registry import build_default_tool_registry


class ContextOrchestrator:
    def __init__(self):
        self.request = None

    async def run(self, request):
        self.request = request
        answer = (
            '{"action":"final","reason":"Eksiksiz.",'
            '"answer":"Mevcut durum: Python projesi tek app.py dosyasıdır.\\n'
            'Mimari yapı: Tek modüldür.\\nRiskler: Test ve katman eksiktir.\\n'
            'Önerilen hedef mimari: core ve tests modülleri ayrılmalıdır.\\n'
            'Geçiş ve doğrulama planı: Önce test, sonra modülerleştirme, '
            'ardından pytest doğrulaması yapılmalıdır."}'
        )
        return OrchestrateResponse(
            answer=answer,
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


@pytest.mark.asyncio
async def test_architect_receives_automatic_project_context(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def topla(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    settings = Settings(
        workspace_root=tmp_path,
        agent_max_steps=8,
        agent_max_model_calls=5,
    )
    orchestrator = ContextOrchestrator()
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=build_default_tool_registry(settings=settings),
    )

    result = await engine.run(
        AgentRequest(
            message="Projeyi incele ve mimarisini açıkla.",
            agent_id="architect",
        )
    )

    assert result.status == "completed"
    assert result.trace[0].action == "context"
    assert result.trace[0].tool == "auto_project_context"
    assert "app.py" in str(result.trace[0].tool_result)
    assert any(
        "AUTO_PROJECT_CONTEXT" in message.content
        for message in orchestrator.request.messages
    )
    assert orchestrator.request.task_type_override == "reasoning"
