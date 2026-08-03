from app.command_ui import COMMAND_UI


def test_command_ui_does_not_blindly_parse_response_json():
    assert "const text=await r.text()" in COMMAND_UI
    assert "Sunucu geçerli JSON döndürmedi" in COMMAND_UI
    assert "const data=await r.json()" not in COMMAND_UI
