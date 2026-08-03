from app.core.schemas import AgentRequest


def test_focused_request_can_disable_auto_context():
    request = AgentRequest(
        message="x",
        agent_id="backend",
        disable_auto_context=True,
        exclusive_write_paths=["score.py"],
    )
    assert request.disable_auto_context is True
