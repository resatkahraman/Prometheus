import asyncio
import time
from typing import Any

import httpx

from app.providers.base import AIProvider, ProviderRequest, ProviderResponse


class OllamaProvider(AIProvider):
    """Small local-model provider backed by Ollama's non-streaming chat API."""

    name = "ollama"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        default_model: str,
        context_tokens: int,
        keep_alive: str,
        timeout_seconds: float,
        expert_model: str | None = None,
        expert_timeout_seconds: float | None = None,
        managed_models: tuple[str, ...] = (),
    ) -> None:
        super().__init__(
            client=client,
            default_model=default_model,
            max_retries=0,
        )
        self.base_url = base_url.rstrip("/")
        self.context_tokens = context_tokens
        self.keep_alive = keep_alive
        self.timeout_seconds = timeout_seconds
        self.expert_model = expert_model
        self.expert_timeout_seconds = expert_timeout_seconds or timeout_seconds
        self.managed_models = {
            default_model,
            *(model for model in managed_models if model),
        }
        self._model_lock = asyncio.Lock()
        self._loaded_model: str | None = None

    async def _unload_previous_model(self, model: str) -> None:
        """Keep only one large Ollama model resident on memory-limited hosts."""
        loaded: set[str] = set()
        try:
            status = await self.client.get(
                f"{self.base_url}/api/ps",
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
            status.raise_for_status()
            payload = status.json()
            loaded = {
                str(item.get("name") or item.get("model") or "")
                for item in payload.get("models", [])
                if isinstance(item, dict)
            }
        except (httpx.HTTPError, ValueError):
            if self._loaded_model:
                loaded.add(self._loaded_model)

        for previous in loaded:
            if previous == model or previous not in self.managed_models:
                continue
            try:
                await self.client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": previous, "keep_alive": 0},
                    timeout=httpx.Timeout(15.0, connect=5.0),
                )
            except httpx.HTTPError:
                pass
        self._loaded_model = None

    @staticmethod
    def _messages(request: ProviderRequest) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": request.system_prompt}]
        messages.extend(
            {
                "role": message.role,
                "content": message.content,
            }
            for message in request.messages
        )
        return messages

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.default_model
        request_timeout = (
            self.expert_timeout_seconds
            if self.expert_model and model == self.expert_model
            else self.timeout_seconds
        )
        payload = {
            "model": model,
            "messages": self._messages(request),
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.context_tokens,
                "num_predict": request.max_output_tokens,
                "temperature": request.temperature,
                "seed": 0,
            },
        }
        started = time.perf_counter()

        async with self._model_lock:
            await self._unload_previous_model(model)
            try:
                response = await self.client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=httpx.Timeout(
                        timeout=request_timeout,
                        connect=10.0,
                        read=request_timeout,
                        write=15.0,
                        pool=10.0,
                    ),
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                self._loaded_model = model
            except (httpx.HTTPError, ValueError) as exc:
                raise RuntimeError(f"Yerel Ollama isteği başarısız: {exc}") from exc

        done_reason = str(data.get("done_reason") or "").strip().lower()
        if done_reason in {"length", "max_tokens"}:
            raise RuntimeError(
                "Yerel model çıktısı token sınırında kesildi; güvenli "
                "fallback gerekli."
            )
        if data.get("done") is False:
            raise RuntimeError("Yerel Ollama cevabı tamamlanmadan sona erdi.")

        message = data.get("message")
        content = (
            message.get("content")
            if isinstance(message, dict)
            else None
        )
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Yerel Ollama modeli boş cevap döndürdü.")

        raw_usage = {
            key: data.get(key)
            for key in (
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
                "done_reason",
            )
            if data.get(key) is not None
        }
        return ProviderResponse(
            provider=self.name,
            model=str(data.get("model") or model),
            content=content.strip(),
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            raw_usage=raw_usage,
            finish_reason=done_reason or None,
        )

    async def availability(self, model: str) -> str:
        """Bounded, read-only model probe; never downloads or starts Ollama."""
        try:
            response = await self.client.get(
                f"{self.base_url}/api/tags",
                timeout=httpx.Timeout(3.0, connect=1.0),
            )
            response.raise_for_status()
            payload = response.json()
            models = payload.get("models")
            if not isinstance(models, list) or not all(isinstance(item, dict) for item in models):
                return "error"
            names = {str(item.get("name") or item.get("model")) for item in models}
            return "available" if model in names else "not_installed"
        except httpx.ConnectError:
            return "unavailable"
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return "error"
