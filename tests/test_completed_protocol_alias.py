from app.agent.protocol import parse_agent_action


def test_completed_alias_is_final_not_a_tool():
    action = parse_agent_action(
        '{"action":"completed","reason":"Görev tamamlandı."}'
    )
    assert action.action == "final"
    assert action.tool is None
    assert action.answer == "Görev tamamlandı."
