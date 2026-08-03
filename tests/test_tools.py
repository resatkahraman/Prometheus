import pytest

from app.tools.base import ToolError
from app.tools.registry import build_default_tool_registry


@pytest.mark.asyncio
async def test_default_registry_contains_worker_tools():
    registry = build_default_tool_registry()
    expected = {
        "calculator",
        "current_datetime",
        "git_diff",
        "git_status",
        "project_summary",
        "safe_terminal",
        "symbolic_math",
        "text_stats",
        "workspace_list",
        "workspace_read",
        "workspace_search",
        "workspace_write",
    }
    assert expected.issubset(set(registry.names()))


@pytest.mark.asyncio
async def test_calculator_tool():
    registry = build_default_tool_registry()
    result = await registry.execute(
        "calculator",
        {"expression": "2 ** 12 * 17"},
    )
    assert result["result"] == 69632


@pytest.mark.asyncio
async def test_calculator_rejects_unsafe_expression():
    registry = build_default_tool_registry()
    with pytest.raises(ToolError):
        await registry.execute(
            "calculator",
            {"expression": "__import__('os').system('echo bad')"},
        )


@pytest.mark.asyncio
async def test_text_stats_tool():
    registry = build_default_tool_registry()
    result = await registry.execute(
        "text_stats",
        {"text": "Adam iki model kullanır."},
    )
    assert result["words"] == 4
