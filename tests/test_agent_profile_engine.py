from app.agent.engine import AgentEngine
from app.core.config import Settings
from app.tools.registry import build_default_tool_registry


def engine():
    tools = build_default_tool_registry()
    return AgentEngine(
        settings=Settings(),
        orchestrator=object(),
        tools=tools,
    )


def test_planner_has_strict_integrity_contract():
    planner = engine().agents.get("planner")
    assert planner.auto_context is True
    assert planner.task_type_override == "reasoning"
    assert "groq_strong" == planner.preferred_routes[0]
    assert any(
        "TASK-001" in instruction
        for instruction in planner.instructions
    )


def test_architect_prefers_gemini():
    architect = engine().agents.get("architect")
    assert architect.preferred_routes[0] == "gemini"
    assert architect.task_type_override == "reasoning"
