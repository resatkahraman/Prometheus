from app.supervisor.failure_intelligence import (
    classify_verification_failure,
)


def test_missing_jest_dom_selects_targeted_dev_install():
    diagnosis = classify_verification_failure(
        result={
            "preset": "npm_test",
            "command": ["npm", "test", "--", "--run"],
            "exit_code": 1,
            "stdout": "",
            "stderr": (
                "Error: [vite-node] Failed to load "
                "@testing-library/jest-dom"
            ),
            "runtime_revision": "terminal-env-v5",
        },
        verification="npm test -- --run",
    )

    assert diagnosis.kind == "missing_frontend_test_package"
    assert diagnosis.retry_arguments == {
        "preset": "npm_install_dev",
        "extra_args": ["@testing-library/jest-dom"],
    }


def test_vitest_globals_failure_uses_command_strategy():
    diagnosis = classify_verification_failure(
        result={
            "preset": "npm_test",
            "command": ["npm", "test", "--", "--run"],
            "exit_code": 1,
            "stdout": "",
            "stderr": "ReferenceError: describe is not defined",
            "runtime_revision": "terminal-env-v5",
        },
        verification="npm test -- --run",
    )

    assert diagnosis.kind == "vitest_global_api_missing"
    assert diagnosis.retry_arguments == {
        "preset": "npm_test",
        "extra_args": ["--run", "--globals"],
    }


def test_node_test_globals_failure_repairs_test_source_instead():
    diagnosis = classify_verification_failure(
        result={
            "preset": "npm_test",
            "command": ["npm", "test"],
            "exit_code": 1,
            "stdout": (
                "> node --test\n"
                "ReferenceError: describe is not defined"
            ),
            "stderr": "",
        },
        verification="npm test",
    )

    assert diagnosis.kind == "node_test_global_api_missing"
    assert diagnosis.retry_tool is None
    assert diagnosis.retry_arguments is None


def test_node_assertion_signature_ignores_runtime_noise():
    first = classify_verification_failure(
        result={
            "preset": "npm_test",
            "command": ["npm", "test"],
            "exit_code": 1,
            "stdout": (
                "✖ rejects invalid collections (0.701ms)\n"
                "AssertionError: Missing expected exception\n"
                "at C:\\workspace\\test\\pricing.test.js:30:10"
            ),
            "stderr": "",
        },
        verification="npm test",
    )
    second = classify_verification_failure(
        result={
            "preset": "npm_test",
            "command": ["npm", "test"],
            "exit_code": 1,
            "stdout": (
                "✖ rejects invalid collections (9.42ms)\n"
                "AssertionError: Missing expected exception\n"
                "at D:\\other\\test\\pricing.test.js:44:7"
            ),
            "stderr": "",
        },
        verification="npm test",
    )

    assert first.signature == second.signature
