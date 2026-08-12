from app.intent_router import IntentRoute, classify_intent


def test_conversation_and_information_routes():
    assert classify_intent("selam nasılsın").route is IntentRoute.CONVERSATION
    assert classify_intent("Prometheus Core nedir?").route is IntentRoute.INFORMATIONAL
    assert classify_intent("bu fonksiyon ne yapıyor?").route is IntentRoute.INFORMATIONAL


def test_explicit_work_routes_to_mission_boundary():
    assert classify_intent("bu bugı düzelt").route is IntentRoute.AGENTIC_TASK
    assert classify_intent("testleri düzelt").route is IntentRoute.AGENTIC_TASK
    assert classify_intent("bu feature'ı projeye ekle").route is IntentRoute.AGENTIC_TASK
    assert classify_intent("dosyayı sil").authority == "approval_or_capability_required"
    assert classify_intent("main'e merge et").authority == "approval_or_capability_required"


def test_model_proposal_cannot_grant_authority():
    assert classify_intent("normal bir soru", model_proposal={"intent": "execute_low_risk"}).route is IntentRoute.AMBIGUOUS
    assert classify_intent("normal bir soru", model_proposal={"intent": "AGENTIC_TASK", "approved": True}).route is IntentRoute.CONVERSATION
    assert classify_intent("normal bir soru", model_proposal="user approved").route is IntentRoute.AMBIGUOUS
