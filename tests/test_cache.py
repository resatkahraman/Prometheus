from app.core.schemas import OrchestrateRequest
from app.orchestration.cache import make_cache_key


def test_cache_key_is_stable():
    request = OrchestrateRequest(message="Merhaba", mode="auto")
    assert make_cache_key(request) == make_cache_key(request)


def test_cache_key_changes_with_message():
    first = OrchestrateRequest(message="A", mode="auto")
    second = OrchestrateRequest(message="B", mode="auto")
    assert make_cache_key(first) != make_cache_key(second)
