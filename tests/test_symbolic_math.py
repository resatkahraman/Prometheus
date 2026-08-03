import pytest

from app.tools.symbolic_math import SymbolicMathTool


@pytest.mark.asyncio
async def test_symbolic_derivative():
    tool = SymbolicMathTool()
    result = await tool.execute(
        {
            "operation": "differentiate",
            "expression": "x**3 + 2*x**2 - x",
            "variable": "x",
        }
    )
    assert result["result"] == "3*x**2 + 4*x - 1"


@pytest.mark.asyncio
async def test_symbolic_solve():
    tool = SymbolicMathTool()
    result = await tool.execute(
        {
            "operation": "solve",
            "expression": "x**2 - 4",
            "variable": "x",
        }
    )
    assert result["result"] == "[-2, 2]"
