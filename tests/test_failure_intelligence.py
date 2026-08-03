from app.supervisor.failure_intelligence import (
    classify_verification_failure,
)


def test_pytest_import_mismatch_selects_importlib_strategy():
    result = {
        "exit_code": 2,
        "success": False,
        "command": ["python", "-m", "pytest", "-q"],
        "stdout": """
ERROR collecting tests/test_score.py
import file mismatch:
imported module 'test_score' has __file__ backend/test_score.py
which is not the same as tests/test_score.py
HINT: remove cached modules
""",
        "stderr": "",
    }
    diagnosis = classify_verification_failure(
        result=result,
        verification="python -m pytest -q",
    )
    assert diagnosis.kind == "pytest_import_mismatch"
    assert diagnosis.retry_arguments == {
        "preset": "pytest",
        "extra_args": ["--import-mode=importlib"],
    }
