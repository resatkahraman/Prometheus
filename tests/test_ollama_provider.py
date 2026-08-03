import json
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.core.schemas import ChatMessage, OrchestrateRequest
from app.orchestration.orchestrator import Orchestrator
from app.providers.base import ProviderRequest, ProviderResponse
from app.providers.ollama import OllamaProvider
from app.storage.operations import OperationsStore


@pytest.mark.asyncio
async def test_ollama_provider_uses_bounded_non_thinking_chat():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b-instruct-2507-q4_K_M",
                "message": {"role": "assistant", "content": "Hazır."},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 42,
                "eval_count": 3,
                "total_duration": 1_000_000,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = OllamaProvider(
            client=client,
            base_url="http://127.0.0.1:11434",
            default_model="qwen3:4b-instruct-2507-q4_K_M",
            context_tokens=4096,
            keep_alive="5m",
            timeout_seconds=180,
        )
        result = await provider.generate(
            ProviderRequest(
                messages=[ChatMessage(role="user", content="Selam")],
                system_prompt="Kısa cevap ver.",
                temperature=0,
                max_output_tokens=1000,
                local=True,
            )
        )

    assert captured["stream"] is False
    assert captured["think"] is False
    assert captured["options"]["num_ctx"] == 4096
    assert captured["options"]["num_predict"] == 1000
    assert result.content == "Hazır."
    assert result.input_tokens == 42
    assert result.output_tokens == 3
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_ollama_provider_rejects_truncated_output():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen3",
                "message": {"content": "eksik"},
                "done": True,
                "done_reason": "length",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = OllamaProvider(
            client=client,
            base_url="http://127.0.0.1:11434",
            default_model="qwen3",
            context_tokens=4096,
            keep_alive="0",
            timeout_seconds=180,
        )
        with pytest.raises(RuntimeError, match="token sınırında kesildi"):
            await provider.generate(
                ProviderRequest(
                    messages=[
                        ChatMessage(role="user", content="Dosya üret")
                    ],
                    system_prompt="Eksiksiz üret.",
                    temperature=0,
                    max_output_tokens=100,
                    local=True,
                )
            )


@pytest.mark.asyncio
async def test_ollama_expert_uses_its_own_longer_http_timeout():
    observed_timeout: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_timeout.update(request.extensions.get("timeout", {}))
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:9b",
                "message": {"content": "Uzman yanıtı."},
                "done": True,
                "done_reason": "stop",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = OllamaProvider(
            client=client,
            base_url="http://127.0.0.1:11434",
            default_model="qwen3.5:4b",
            context_tokens=4096,
            keep_alive="2m",
            timeout_seconds=90,
            expert_model="qwen3.5:9b",
            expert_timeout_seconds=180,
        )
        result = await provider.generate(
            ProviderRequest(
                messages=[ChatMessage(role="user", content="Kod üret")],
                system_prompt="Eksiksiz üret.",
                temperature=0,
                max_output_tokens=100,
                model="qwen3.5:9b",
                local=True,
            )
        )

    assert result.model == "qwen3.5:9b"
    assert observed_timeout["read"] == 180


class LocalProvider:
    default_model = "qwen3"

    async def generate(self, _request):
        return ProviderResponse(
            provider="ollama",
            model="qwen3",
            content="Yerel ve doğrulanabilir anlamlı cevap.",
            latency_ms=5,
            input_tokens=12,
            output_tokens=6,
            finish_reason="stop",
        )


class LocalRegistry:
    def __init__(self):
        self.provider = LocalProvider()

    def names(self):
        return ["ollama"]

    def get_optional(self, name):
        return self.provider if name == "ollama" else None

    def get(self, name):
        if name != "ollama":
            raise ValueError(name)
        return self.provider


@pytest.mark.asyncio
async def test_local_calls_do_not_consume_remote_mission_budget(
    tmp_path: Path,
):
    settings = Settings(
        _env_file=None,
        local_model_enabled=True,
        cache_enabled=False,
        mission_max_model_calls=1,
        operations_database_path=tmp_path / "operations.db",
        usage_log_path=tmp_path / "usage.jsonl",
    )
    store = OperationsStore(settings.operations_database_path)
    await store.initialize()
    orchestrator = Orchestrator(
        settings=settings,
        registry=LocalRegistry(),
        store=store,
    )
    request = OrchestrateRequest(
        message="Kısa yerel görev.",
        mode="direct",
        provider="local_qwen",
        usage_scope="local-mission",
    )

    assert (await orchestrator.run(request)).answer
    assert (await orchestrator.run(request)).answer
    assert await store.mission_usage("local-mission") is None
