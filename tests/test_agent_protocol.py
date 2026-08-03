import pytest

from app.agent.protocol import AgentProtocolError, parse_agent_action


def test_parse_tool_action():
    raw = (
        '{"action":"tool","reason":"Hesap gerekli.",'
        '"tool":"calculator","arguments":{"expression":"2+2"}}'
    )
    action = parse_agent_action(raw)
    assert action.action == "tool"
    assert action.tool == "calculator"
    assert action.arguments == {"expression": "2+2"}


def test_parse_fenced_final_action():
    action = parse_agent_action(
        '```json\n{"action":"final","answer":"Sonuç 4."}\n```'
    )
    assert action.action == "final"
    assert action.answer == "Sonuç 4."


def test_invalid_protocol_is_rejected():
    with pytest.raises(AgentProtocolError):
        parse_agent_action("normal metin")
