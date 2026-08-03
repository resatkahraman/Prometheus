from app.supervisor.failure_intelligence import classify_verification_failure


def test_old_esbuild_child_node_path_failure_gets_single_runtime_retry():
    diagnosis = classify_verification_failure(
        result={
            "preset": "npm_install",
            "exit_code": 1,
            "success": False,
            "runtime_revision": "legacy",
            "stderr": "npm error command cmd.exe /c node install.js\\n'node' is not recognized as an internal or external command",
        },
        verification="npm test -- --run",
    )
    assert diagnosis.kind == "npm_child_node_path_missing"
    assert diagnosis.retry_arguments == {"preset": "npm_install", "extra_args": []}
    assert diagnosis.strategy_key == "npm_install_repaired_path"
