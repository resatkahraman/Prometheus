from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentRequest
from app.tools.base import ToolError
from app.tools.registry import build_default_tool_registry


def test_agent_request_contains_exact_write_contract():
    request = AgentRequest(
        message="test",
        agent_id="backend",
        exclusive_write_paths=["score.py", "tests/test_score.py"],
    )
    assert request.exclusive_write_paths == [
        "score.py",
        "tests/test_score.py",
    ]


def test_exact_profile_scope_blocks_alternative_backend_path(
    tmp_path: Path,
):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    agents = build_default_agent_registry(tools.names())
    profile = agents.get("backend").model_copy(
        update={"write_paths": ["score.py", "tests/test_score.py"]}
    )

    with pytest.raises(ToolError):
        agents.authorize(
            profile=profile,
            tool_name="workspace_write",
            arguments={
                "path": "backend/score.py",
                "content": "x = 1\n",
            },
        )

    agents.authorize(
        profile=profile,
        tool_name="workspace_write",
        arguments={
            "path": "score.py",
            "content": "x = 1\n",
        },
    )
