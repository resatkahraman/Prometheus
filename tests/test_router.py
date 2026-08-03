from app.core.schemas import ChatMessage
from app.orchestration.router import TaskClassifier


def test_classifier_detects_code():
    classifier = TaskClassifier()
    result = classifier.classify(
        [ChatMessage(role="user", content="FastAPI kodumu düzelt")]
    )
    assert result == "coding"


def test_classifier_detects_summary():
    classifier = TaskClassifier()
    result = classifier.classify(
        [ChatMessage(role="user", content="Bu metni özetle")]
    )
    assert result == "summarization"


def test_classifier_detects_general():
    classifier = TaskClassifier()
    result = classifier.classify(
        [ChatMessage(role="user", content="Bugün nasılsın?")]
    )
    assert result == "general"
