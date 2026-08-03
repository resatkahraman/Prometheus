from app.command_ui import COMMAND_UI


def test_ui_has_single_action_center_and_approval_context():
    assert "Eylem Merkezi" in COMMAND_UI
    assert "sıradaki tek aktif onaydır" in COMMAND_UI
    assert "Neden gerekli?" in COMMAND_UI
    assert "Etkilenen hedef" in COMMAND_UI
    assert "Sonraki aşama" in COMMAND_UI
    assert "Onayla ve Uygula" in COMMAND_UI


def test_every_error_surface_is_copyable():
    assert "Hata Raporu" in COMMAND_UI
    assert "Tanılamayı Kopyala" in COMMAND_UI
    assert "Agent çıktısı" in COMMAND_UI
    assert "Reviewer kararı" in COMMAND_UI
    assert "navigator.clipboard" in COMMAND_UI
    assert "document.execCommand" in COMMAND_UI


def test_no_distracting_telemetry_or_interval():
    assert "Canlı Telemetri" not in COMMAND_UI
    assert "setInterval(" not in COMMAND_UI
    assert "@keyframes" not in COMMAND_UI


def test_decision_input_keeps_draft():
    assert "const drafts=new Map()" in COMMAND_UI
    assert "editingDecisionId" in COMMAND_UI
    assert "saveDrafts()" in COMMAND_UI
