from app.chat_ui import CHAT_UI


def test_v06_ui():
    for marker in (
        "Prometheus",
        "v0.8.0",
        "Agent Army Console",
        'id="agentProfile"',
        "/v1/agents",
        "agent_id:agentSelect.value",
        "approvalCard",
        "prometheus.chat.v080",
        "adam_chat_v0717",
    ):
        assert marker in CHAT_UI
