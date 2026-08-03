from pathlib import Path
import pytest
from app.agent.engine import AgentEngine
from app.core.config import Settings
from app.core.schemas import AgentRequest,OrchestrateResponse
from app.tools.registry import build_default_tool_registry
class O:
    def __init__(self): self.calls=0
    async def run(self,request):
        self.calls+=1
        return OrchestrateResponse(answer='{"action":"final","reason":"ok","answer":"Kontrol başarılı."}',mode='auto',selected_route='github',selected_provider='github',model='test',latency_ms=1,task_type='coding',route_reason='test',calls_used=1,routing_scores=[])
@pytest.mark.asyncio
async def test_approval_before_model(tmp_path:Path):
    (tmp_path/'app.py').write_text('def a():\n    return 1\n',encoding='utf-8')
    settings=Settings(workspace_root=tmp_path,agent_max_steps=5,agent_max_model_calls=5); o=O(); e=AgentEngine(settings=settings,orchestrator=o,tools=build_default_tool_registry(settings=settings))
    first=await e.run(AgentRequest(message='Projede Python sözdizimi kontrolünü çalıştır.',agent_id='worker'))
    assert first.status=='awaiting_approval' and first.model_calls_used==0 and o.calls==0
    second=await e.approve(session_id=first.session_id,approval_id=first.pending_approval.id)
    assert second.status=='completed' and second.model_calls_used==1 and second.trace[0].tool_result['success'] is True
