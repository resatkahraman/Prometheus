from app.tools.fingerprint import tool_fingerprint


def test_workspace_fingerprint_normalizes_slashes():
    left = tool_fingerprint(
        "workspace_write",
        {"path": r"tests\test_score.py", "content": "x\n"},
    )
    right = tool_fingerprint(
        "workspace_write",
        {"path": "tests/test_score.py", "content": "x\n"},
    )
    assert left == right


def test_different_content_has_different_fingerprint():
    left = tool_fingerprint(
        "workspace_write",
        {"path": "score.py", "content": "a\n"},
    )
    right = tool_fingerprint(
        "workspace_write",
        {"path": "score.py", "content": "b\n"},
    )
    assert left != right
