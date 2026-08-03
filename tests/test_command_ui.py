from app.command_ui import COMMAND_UI


def test_mission_control_is_mobile_responsive():
    assert "Prometheus · Mission Control" in COMMAND_UI
    assert "@media(max-width:820px)" in COMMAND_UI
    assert "/v1/supervisor/commands" in COMMAND_UI
    assert "Sıradaki Görevi Başlat" in COMMAND_UI
    assert "Görev İnceleyici" in COMMAND_UI
