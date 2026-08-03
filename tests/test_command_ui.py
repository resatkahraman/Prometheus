from app.command_ui import COMMAND_UI


def test_mission_control_is_mobile_responsive():
    assert "Prometheus · Mission Control" in COMMAND_UI
    assert "@media(max-width:820px)" in COMMAND_UI
    assert "/v1/supervisor/commands" in COMMAND_UI
    assert "Sıradaki Görevi Başlat" in COMMAND_UI
    assert "Görev İnceleyici" in COMMAND_UI


def test_project_run_console_ui_elements_in_lab_ui():
    from app.lab_ui import LAB_UI

    assert "Project Run Console" in LAB_UI
    assert "Preview is deterministic and does not call a model or change files." in LAB_UI
    assert 'id="projectRunWorkspace"' in LAB_UI
    assert 'id="projectRunGoal"' in LAB_UI
    assert 'id="projectRunPreviewBtn"' in LAB_UI
    assert 'id="projectRunPreviewCard"' in LAB_UI
    assert 'id="projectRunPreviewTasks"' in LAB_UI
    assert 'id="projectRunExactFiles"' in LAB_UI
    assert 'id="projectRunVerifications"' in LAB_UI
    assert 'id="projectRunWarnings"' in LAB_UI
    assert 'id="projectRunUsage"' in LAB_UI
    assert 'id="projectRunApprovalGate"' in LAB_UI
    assert "previewProjectRun()" in LAB_UI
    assert "renderProjectRunPreview(" in LAB_UI

