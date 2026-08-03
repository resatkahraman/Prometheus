from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.tools.registry import build_default_tool_registry


class FalseClaimThenWrite:
    def __init__(self):
        self.calls = 0

    async def run(self, request):
        self.calls += 1
        if self.calls == 1:
            answer = (
                '{"action":"final","reason":"Hazır.",'
                '"answer":"src/components/Button.tsx dosyası oluşturuldu."}'
            )
        elif self.calls == 2:
            answer = (
                '{"action":"tool","reason":"Gerçek dosya yazma kanıtı gerekli.",'
                '"tool":"workspace_write","arguments":'
                '{"path":"src/components/Button.tsx",'
                '"content":"export default function Button(){return null;}"}'
                "}"
            )
        else:
            answer = (
                '{"action":"final","reason":"Gerçek yazma tamamlandı.",'
                '"answer":"src/components/Button.tsx dosyası oluşturuldu.\\n'
                'Doğrulama Durumu: test edilmedi; package.json bulunmuyor."}'
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


@pytest.mark.asyncio
async def test_false_write_claim_is_retried_then_requires_approval(
    tmp_path: Path,
):
    (tmp_path / "src" / "components").mkdir(parents=True)
    settings = Settings(
        workspace_root=tmp_path,
        agent_max_steps=8,
        agent_max_model_calls=8,
        agent_quality_max_retries=2,
    )
    orchestrator = FalseClaimThenWrite()
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=build_default_tool_registry(settings=settings),
    )

    first = await engine.run(
        AgentRequest(
            message="src/components/Button.tsx dosyasını oluştur.",
            agent_id="frontend",
        )
    )

    assert first.status == "awaiting_approval"
    assert first.pending_approval.tool_name == "workspace_write"
    assert any(
        step.action == "quality_rejected"
        for step in first.trace
    )

    second = await engine.approve(
        session_id=first.session_id,
        approval_id=first.pending_approval.id,
    )
    assert second.status == "completed"
    assert (tmp_path / "src" / "components" / "Button.tsx").exists()
