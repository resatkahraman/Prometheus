from app.command_ui import COMMAND_UI


def test_professional_ui_has_action_center_task_table_and_inspector():
    assert "Prometheus · Mission Control" in COMMAND_UI
    assert "Eylem Merkezi" in COMMAND_UI
    assert "Görev Portföyü" in COMMAND_UI
    assert "Görev İnceleyici" in COMMAND_UI
    assert "Aktivite ve Tanılama" in COMMAND_UI
    assert "Onayla ve Uygula" in COMMAND_UI


def test_ui_prevents_double_click_and_sends_expected_identity():
    assert "approvalInFlight=new Set()" in COMMAND_UI
    assert "approval_id:approvalId" in COMMAND_UI
    assert "approval_version:version" in COMMAND_UI
    assert "background:true" in COMMAND_UI


def test_ui_has_no_distracting_animation_or_telemetry():
    assert "Canlı Telemetri" not in COMMAND_UI
    assert "@keyframes" not in COMMAND_UI
    assert "setInterval(" not in COMMAND_UI
