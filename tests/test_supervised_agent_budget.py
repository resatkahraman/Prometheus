from app.core.schemas import AgentRequest


def test_supervisor_request_supports_explicit_budget():
    request = AgentRequest(
        message="test",
        agent_id="backend",
        max_steps=24,
        max_model_calls=28,
        supervised_budget=True,
    )
    assert request.max_steps == 24
    assert request.max_model_calls == 28
    assert request.supervised_budget is True
