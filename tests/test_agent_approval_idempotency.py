import asyncio
from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.approvals.manager import ApprovalManager
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.tools.registry import build_default_tool_registry


class Orchestrator:
    def __init__(self):
        self.calls = 0

    async def run(self, request):
        self.calls += 1
        if self.calls == 1:
            answer = (
                '{"action":"tool","reason":"write",'
                '"tool":"workspace_write","arguments":'
                '{"path":"once.txt","content":"one"}}'
            )
        else:
            await asyncio.sleep(0.03)
            answer = (
                '{"action":"final","reason":"done",'
                '"answer":"Dosya oluşturuldu.\\n'
                'Doğrulama Durumu: test edilmedi; metin dosyası."}'
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
async def test_duplicate_concurrent_approve_replays_same_response(
    tmp_path: Path,
):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(
        settings=settings,
        approvals=ApprovalManager(ttl_seconds=300),
    )
    orchestrator = Orchestrator()
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=tools,
    )
    first = await engine.run(AgentRequest(message="once.txt oluştur"))
    responses = await asyncio.gather(
        engine.approve(
            session_id=first.session_id,
            approval_id=first.pending_approval.id,
        ),
        engine.approve(
            session_id=first.session_id,
            approval_id=first.pending_approval.id,
        ),
    )
    assert responses[0].status == "completed"
    assert responses[1].status == "completed"
    assert orchestrator.calls == 2
    assert (tmp_path / "once.txt").read_text(encoding="utf-8") == "one"
