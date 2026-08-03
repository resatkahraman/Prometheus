from app.planning.integrity import validate_planning_document
from app.planning.models import PlanEvidence, PlanningDocument, PlanTask


def test_mutating_worker_without_exact_files_is_invalid():
    document = PlanningDocument(
        verified_facts=["[file:app.py] app.py mevcut"],
        assumptions=["Yok"],
        critical_decisions=["Yok"],
        tasks=[
            PlanTask(
                id="TASK-001",
                title="Uygulamayı değiştir",
                priority="zorunlu",
                assigned_agent="worker",
                evidence=[PlanEvidence(type="user_request", value="değiştir")],
                acceptance_criteria=["Gerçek test exit code 0 olmalı."],
                dependencies=[],
                dependency_reason="yok",
                parallelizable="evet",
                verification="python -m pytest -q",
                user_approval="gerekli",
                exact_files=[],
            )
        ],
    )

    result = validate_planning_document(document, known_agents={"worker"})
    assert result.valid is False
    assert any("Kesin Dosyalar" in error for error in result.errors)
