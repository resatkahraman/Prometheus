from app.core.config import Settings
from app.orchestration.routes import RouteCatalog


class FakeRegistry:
    def get_optional(self, name):
        return object() if name in {"gemini", "github", "groq"} else None


def test_route_catalog_has_local_and_four_remote_routes():
    catalog = RouteCatalog(
        settings=Settings(),
        registry=FakeRegistry(),
    )
    assert [route.key for route in catalog.all()] == [
        "local_qwen",
        "local_expert",
        "local_structured",
        "gemini",
        "github",
        "groq_fast",
        "groq_strong",
    ]
