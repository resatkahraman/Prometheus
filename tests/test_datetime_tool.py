import pytest

from app.tools.base import ToolError
from app.tools.datetime_tool import CurrentDateTimeTool


@pytest.mark.asyncio
async def test_datetime_requires_timezone():
    tool = CurrentDateTimeTool()
    with pytest.raises(ToolError):
        await tool.execute({})


@pytest.mark.asyncio
async def test_istanbul_alias_and_offset():
    tool = CurrentDateTimeTool()
    result = await tool.execute({"timezone": "Istanbul"})
    assert result["timezone"] == "Europe/Istanbul"
    assert result["utc_offset"] == "+03:00"
    assert result["weekday"] in {
        "Pazartesi",
        "Salı",
        "Çarşamba",
        "Perşembe",
        "Cuma",
        "Cumartesi",
        "Pazar",
    }
