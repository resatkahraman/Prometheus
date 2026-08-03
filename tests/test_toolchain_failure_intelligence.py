from app.supervisor.failure_intelligence import (
    classify_verification_failure,
)


def test_missing_npm_selects_explicit_node_setup():
    diagnosis = classify_verification_failure(
        result={
            "preset": "npm_test",
            "exit_code": 127,
            "success": False,
            "failure_kind": "missing_command",
            "missing_command": "npm",
            "stderr": "Komut bulunamadı: npm",
        },
        verification="npm test -- --run",
    )

    assert diagnosis.kind == "missing_node_toolchain"
    assert diagnosis.strategy_key == "install_node_lts"
    assert diagnosis.retry_arguments == {
        "preset": "install_node_lts",
        "extra_args": [],
    }


def test_missing_vitest_selects_npm_install():
    diagnosis = classify_verification_failure(
        result={
            "preset": "npm_test",
            "exit_code": 1,
            "success": False,
            "command": ["npm", "test", "--", "--run"],
            "stdout": "'vitest' is not recognized as an internal "
            "or external command",
            "stderr": "",
        },
        verification="npm test -- --run",
    )

    assert diagnosis.kind == "npm_dependencies_not_installed"
    assert diagnosis.strategy_key == "npm_install"
    assert diagnosis.retry_arguments == {
        "preset": "npm_install",
        "extra_args": [],
    }


def test_missing_specific_frontend_package_goes_to_code_repair():
    diagnosis = classify_verification_failure(
        result={
            "preset": "npm_test",
            "exit_code": 1,
            "success": False,
            "command": ["npm", "test", "--", "--run"],
            "stdout": (
                "Error: Cannot find package "
                "'@testing-library/jest-dom'"
            ),
            "stderr": "",
        },
        verification="npm test -- --run",
    )

    assert diagnosis.kind == "missing_frontend_test_package"
    assert diagnosis.retry_tool == "safe_terminal"
    assert diagnosis.retry_arguments == {
        "preset": "npm_install_dev",
        "extra_args": ["@testing-library/jest-dom"],
    }
