import pytest
from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.tools.base import ToolError
from app.tools.registry import build_default_tool_registry

def R():
    tools=build_default_tool_registry(settings=Settings()); return build_default_agent_registry(tools.names())
def test_profiles(): assert R().ids()==['worker','planner','architect','frontend','backend','database','qa','reviewer','integration','calculation']
def test_planner_read_only():
    p=R().get('planner'); assert p.read_only and 'workspace_write' not in p.allowed_tools
def test_frontend_blocks_backend():
    r=R(); p=r.get('frontend')
    with pytest.raises(ToolError): r.authorize(profile=p,tool_name='workspace_write',arguments={'path':'backend/a.py','content':'x'})
def test_frontend_allows_component():
    r=R(); r.authorize(profile=r.get('frontend'),tool_name='workspace_write',arguments={'path':'src/components/A.tsx','content':'x'})
