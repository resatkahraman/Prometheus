from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.approvals.manager import ApprovalManager
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
                '{"action":"tool","reason":"Dosya oluşturulmalı.",'
                '"tool":"workspace_write","arguments":'
                '{"path":"created.txt","content":"Adam"}}'
            )
        else:
            answer = (
                '{"action":"final","reason":"Dosya oluşturuldu.",'
                '"answer":"Dosya oluşturuldu.\\n'
                'Doğrulama Durumu: test edilmedi; bu görev yalnızca '
                'metin dosyası oluşturmayı kapsıyor."}'
            )

        return OrchestrateResponse(
            answer=answer,
            mode="auto",
            selected_route="groq_strong",
            selected_provider="groq",
            model="llama-test",
            latency_ms=10,
            task_type="coding",
            route_reason="test",
            calls_used=1,
            routing_scores=[],
        )


@pytest.mark.asyncio
async def test_agent_resumes_after_write_approval(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        agent_max_steps=5,
        agent_max_model_calls=6,
    )
    registry = build_default_tool_registry(
        settings=settings,
        approvals=ApprovalManager(ttl_seconds=300),
    )
    engine = AgentEngine(
        settings=settings,
        orchestrator=FakeOrchestrator(),
        tools=registry,
    )

    first = await engine.run(
        AgentRequest(message="created.txt oluştur")
    )
    assert first.status == "awaiting_approval"
    assert not (tmp_path / "created.txt").exists()

    second = await engine.approve(
        session_id=first.session_id,
        approval_id=first.pending_approval.id,
    )
    assert second.status == "completed"
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "Adam"
