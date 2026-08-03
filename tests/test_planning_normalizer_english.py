from app.planning.parser import parse_planning_document


PLAN = """
## Verified Project Facts
- [file:app.py] Python file exists.

## Assumptions
- None

## Tasks
### TASK-001: Add tests
- Priority: mandatory
- Assigned Agent: qa
- Evidence: file:app.py
- Acceptance Criteria:
  - pytest exit code must be 0.
- Dependencies: none
- Dependency Reason: none
- Parallelizable: yes
- Verification: python -m pytest -q
- User Approval: not required
- Exact Files: none

## Critical User Decisions
- None
"""


def test_english_field_aliases_parse():
    document = parse_planning_document(PLAN)
    task = document.tasks[0]
    assert task.title == "Add tests"
    assert task.priority == "zorunlu"
    assert task.assigned_agent == "qa"
    assert task.parallelizable == "evet"
    assert task.user_approval == "gerekmez"
