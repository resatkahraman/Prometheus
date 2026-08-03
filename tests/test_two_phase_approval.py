import asyncio
from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentRequest
from app.orchestration.orchestrator import Orchestrator
from app.tools.registry import build_default_tool_registry


def test_engine_exposes_two_phase_approval_api():
    assert hasattr(AgentEngine, "apply_approval")
    assert hasattr(AgentEngine, "continue_after_approval")
    assert hasattr(AgentEngine, "abandon_session")
