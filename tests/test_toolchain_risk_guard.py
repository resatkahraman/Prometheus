from app.tools.registry import ToolRegistry


def test_node_and_dependency_setup_always_require_explicit_approval():
    assert ToolRegistry.is_high_risk(
        "safe_terminal",
        {"preset": "install_node_lts"},
    )
    assert ToolRegistry.is_high_risk(
        "safe_terminal",
        {"preset": "npm_install"},
    )
