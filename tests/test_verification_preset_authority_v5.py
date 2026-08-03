from app.supervisor.models import SupervisorTask
from app.supervisor.service import SupervisorService


def task() -> SupervisorTask:
    return SupervisorTask(
        id="TASK-002",
        title="frontend",
        priority="zorunlu",
        assigned_agent="frontend",
        evidence=[],
        acceptance_criteria=["test"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification="npm test -- --run",
        user_approval="gerekli",
        exact_files=["src/X.test.tsx"],
    )


def test_dependency_install_is_not_test_evidence():
    assert not SupervisorService._verification_command_matches(
        task(),
        {
            "preset": "npm_install_dev",
            "command": [
                "npm",
                "install",
                "--save-dev",
                "@testing-library/jest-dom",
            ],
            "exit_code": 0,
            "success": True,
        },
    )


def test_npm_test_preset_is_authoritative():
    assert SupervisorService._verification_command_matches(
        task(),
        {
            "preset": "npm_test",
            "command": ["npm", "test", "--", "--run", "--globals"],
            "exit_code": 0,
            "success": True,
        },
    )


def test_file_exists_preset_is_authoritative_for_access_sync():
    static_task = task()
    static_task.verification = "node -e \"require('fs').accessSync('planet.html')\""
    static_task.exact_files = ["planet.html"]
    assert SupervisorService._verification_command_matches(
        static_task,
        {
            "preset": "file_exists",
            "command": ["python", "-c", "<workspace file check>", "planet.html"],
            "exit_code": 0,
            "success": True,
        },
    )
