from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.improvement.store import ImprovementStore
from app.improvement.service import ImprovementService
from app.orchestration.routes import RouteCatalog
from app.providers.ollama import OllamaProvider


class _Registry:
    def get_optional(self, _name: str):
        return object()


def _settings(tmp_path):
    return Settings(_env_file=None, workspace_root=tmp_path, improvement_database_path=tmp_path / "improvement.db", operations_database_path=tmp_path / "ops.db")


def test_canonical_local_stack_and_capability_registry(tmp_path):
    settings = _settings(tmp_path)
    assert settings.ollama_model == "gemma4:e4b-it-qat"
    assert settings.ollama_embedding_model == "embeddinggemma:300m-qat-q4_0"
    assert settings.ollama_structured_model == "ministral-3:3b"
    assert "qwen3.5" not in settings.ollama_model
    assert "qwen3.5" not in settings.ollama_expert_model
    routes = {route.key: route for route in RouteCatalog(settings=settings, registry=_Registry()).all()}
    assert "general_chat" in routes["local_qwen"].capabilities
    assert routes["local_structured"].model == "ministral-3:3b"
    assert "tool_routing" in routes["local_structured"].capabilities


@pytest.mark.asyncio
async def test_ollama_availability_states_are_truthful():
    def tags(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "gemma4:e4b-it-qat"}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(tags)) as client:
        provider = OllamaProvider(client=client, base_url="http://127.0.0.1:11434", default_model="gemma4:e4b-it-qat", context_tokens=4096, keep_alive="5m", timeout_seconds=20)
        assert await provider.availability("gemma4:e4b-it-qat") == "available"
        assert await provider.availability("ministral-3:3b") == "not_installed"

    async def unavailable(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")
    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        provider = OllamaProvider(client=client, base_url="http://127.0.0.1:11434", default_model="gemma4:e4b-it-qat", context_tokens=4096, keep_alive="5m", timeout_seconds=20)
        assert await provider.availability("gemma4:e4b-it-qat") == "unavailable"

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"models": "invalid"}))) as client:
        provider = OllamaProvider(client=client, base_url="http://127.0.0.1:11434", default_model="gemma4:e4b-it-qat", context_tokens=4096, keep_alive="5m", timeout_seconds=20)
        assert await provider.availability("gemma4:e4b-it-qat") == "error"


@pytest.mark.asyncio
async def test_embedding_provenance_blocks_mixed_vector_spaces(tmp_path):
    store = ImprovementStore(tmp_path / "improvement.db")
    entry = await store.upsert_orientation(project_key="project", path="a.py", source_sha256="a" * 64, kind="outline", content="alpha", embedding=[1.0, 0.0], embedding_model="qwen3-embedding:0.6b")
    rows, _ = await store.recall_rows(project_key="project")
    assert rows[0]["embedding_model"] == "qwen3-embedding:0.6b"
    assert rows[0]["embedding_dimensions"] == 2
    await store.set_orientation_embedding(entry, [0.0, 1.0], "embeddinggemma:300m-qat-q4_0")
    rows, _ = await store.recall_rows(project_key="project")
    assert rows[0]["embedding_model"] == "embeddinggemma:300m-qat-q4_0"


@pytest.mark.asyncio
async def test_legacy_embedding_requires_explicit_rebuild(tmp_path):
    service = ImprovementService(_settings(tmp_path))
    await service.store.upsert_orientation(project_key=service.project_key, path="legacy.py", source_sha256="b" * 64, kind="outline", content="legacy", embedding=[1.0, 0.0], embedding_model="qwen3-embedding:0.6b")

    class _Embedding:
        async def embed(self, _texts):
            raise AssertionError("legacy vectors must not be automatically re-embedded")

    service.embedding = _Embedding()
    result = await service.index_workspace(max_files=1, build_embeddings=True)
    assert result["incompatible_embeddings"] == 1
    assert result["embedding_rebuild_required"] is True
    assert result["embedded_entries"] == 0


def test_models_remain_untrusted_processors_not_authority_sources():
    source = __import__("pathlib").Path("app/providers/ollama.py").read_text(encoding="utf-8")
    assert "tool" not in source.casefold() or "generate" in source
    assert "subprocess" not in source
    assert "ollama pull" not in source
