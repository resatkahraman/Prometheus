from app.command_ui import COMMAND_UI


def test_ui_blocks_second_task_while_one_is_active():
    assert "Paylaşılan workspace güvenli biçimde seri çalışır" in COMMAND_UI
    assert "const activeWork=c.tasks.some" in COMMAND_UI
    assert "Önce ${active.id} aktif görevini tamamla" in COMMAND_UI


def test_ui_keeps_copyable_diagnostics():
    assert "Tüm Hataları Kopyala" in COMMAND_UI
    assert "Tanılama" in COMMAND_UI
    assert "navigator.clipboard" in COMMAND_UI
