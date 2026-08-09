from app.security.pandora import PANDORA_MISSION_CONTROL_REVISION, PandoraSessionManager


def test_mobile_control_revision_and_token_shape() -> None:
    manager = PandoraSessionManager()
    assert PANDORA_MISSION_CONTROL_REVISION == "pandora-mobile-mission-control-v1"
    assert manager.mobile_approval_token(None, command_id="cmd", approval_id="app", approval_version=1) is None
    assert not manager.mobile_approval_token_is_valid(None, command_id="cmd", approval_id="app", approval_version=1, control_token="pmc1_" + "0" * 64)
