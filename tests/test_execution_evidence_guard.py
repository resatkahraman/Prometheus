from types import SimpleNamespace

from app.agents.execution_evidence import inspect_execution_evidence


def write_step(path: str):
    return SimpleNamespace(
        tool="workspace_write",
        tool_result={
            "changed": True,
            "path": path,
        },
    )


def test_create_request_without_write_tool_is_rejected():
    result = inspect_execution_evidence(
        user_text="src/components/Button.tsx dosyasını oluştur.",
        answer="Dosyayı oluşturdum.",
        trace=[],
    )
    assert result.accepted is False
    assert "workspace_write" in result.reason


def test_create_request_with_matching_write_is_accepted():
    result = inspect_execution_evidence(
        user_text="src/components/Button.tsx dosyasını oluştur.",
        answer="src/components/Button.tsx dosyası oluşturuldu.",
        trace=[write_step("src/components/Button.tsx")],
    )
    assert result.accepted is True


def test_wrong_written_path_is_rejected():
    result = inspect_execution_evidence(
        user_text="src/components/Button.tsx dosyasını oluştur.",
        answer="Dosya oluşturuldu.",
        trace=[write_step("src/components/Other.tsx")],
    )
    assert result.accepted is False
    assert "src/components/button.tsx" in result.reason.casefold()


def test_completion_claim_without_user_write_request_is_still_rejected():
    result = inspect_execution_evidence(
        user_text="Bu dosyayı incele.",
        answer="Dosya güncellendi.",
        trace=[],
    )
    assert result.accepted is False
