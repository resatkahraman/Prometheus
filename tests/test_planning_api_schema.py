from app.core.schemas import (
    PlanningTaskPreview,
    PlanningValidateResponse,
)


def test_planning_validation_schema():
    response = PlanningValidateResponse(
        valid=True,
        execution_layers=[["TASK-001"]],
        tasks=[
            PlanningTaskPreview(
                id="TASK-001",
                title="Test",
                priority="zorunlu",
                assigned_agent="qa",
                evidence=[
                    {
                        "type": "file",
                        "value": "app.py",
                    }
                ],
                dependencies=[],
                parallelizable="evet",
                user_approval="gerekmez",
            )
        ],
    )
    assert response.tasks[0].assigned_agent == "qa"
