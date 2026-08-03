from app.supervisor.models import SupervisorTask
from app.supervisor.service import SupervisorService


def make_task(verification: str) -> SupervisorTask:
    return SupervisorTask(
        id="TASK-001",
        title="x",
        priority="zorunlu",
        assigned_agent="qa",
        evidence=[],
        acceptance_criteria=["x"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="hayır",
        verification=verification,
        user_approval="gerekli",
        exact_files=["x.py"],
    )


def test_pytest_verification_is_deterministic():
    assert SupervisorService._verification_arguments(
        make_task("python -m pytest -q")
    ) == {"preset": "pytest", "extra_args": []}


def test_focused_pytest_file_is_forwarded_safely():
    assert SupervisorService._verification_arguments(
        make_task(
            "python -m pytest -q "
            "tests/test_task_api_backend_contract.py"
        )
    ) == {
        "preset": "pytest",
        "extra_args": ["tests/test_task_api_backend_contract.py"],
    }


def test_focused_pytest_node_id_is_forwarded_safely():
    assert SupervisorService._verification_arguments(
        make_task(
            "pytest tests/test_task_api_backend_contract.py::"
            "test_title_validation_contract"
        )
    ) == {
        "preset": "pytest",
        "extra_args": [
            "tests/test_task_api_backend_contract.py::"
            "test_title_validation_contract"
        ],
    }


def test_unsafe_or_arbitrary_pytest_arguments_are_rejected():
    assert SupervisorService._verification_arguments(
        make_task("pytest -p malicious_plugin")
    ) is None
    assert SupervisorService._verification_arguments(
        make_task("pytest ../outside.py")
    ) is None


def test_vitest_verification_is_deterministic():
    assert SupervisorService._verification_arguments(
        make_task("npm test -- --run")
    ) == {"preset": "npm_test", "extra_args": ["--run"]}


def test_focused_node_test_file_is_forwarded_through_npm():
    assert SupervisorService._verification_arguments(
        make_task("npm test -- test/pricing.contract.test.js")
    ) == {
        "preset": "npm_test",
        "extra_args": ["test/pricing.contract.test.js"],
    }


def test_unscoped_npm_test_is_isolated_to_exact_task_tests():
    task = make_task("npm test")
    task.exact_files = [
        "package.json",
        "src/calculator.js",
        "tests/calculator.test.js",
    ]

    assert SupervisorService._verification_arguments(task) == {
        "preset": "npm_test",
        "extra_args": ["tests/calculator.test.js"],
    }


def test_node_test_verification_is_supported():
    task = make_task("node --test tests/earth.test.js")
    task.exact_files = ["tests/earth.test.js"]
    assert SupervisorService._verification_arguments(task) == {
        "preset": "node_test",
        "extra_args": ["tests/earth.test.js"],
    }


def test_static_html_access_check_uses_file_exists_preset():
    task = make_task("node -e \"require('fs').accessSync('planet.html')\"")
    task.exact_files = ["planet.html"]
    assert SupervisorService._verification_arguments(task) == {
        "preset": "file_exists",
        "extra_args": ["planet.html"],
    }
