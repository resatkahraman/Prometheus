import asyncio
import time
from typing import Any

import httpx

from app.core.schemas import CatalogModel
from app.providers.base import AIProvider, ProviderRequest, ProviderResponse


def _header_int(headers: httpx.Headers, name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        base_url: str,
        default_model: str,
        max_retries: int,
    ) -> None:
        super().__init__(
            client=client,
            default_model=default_model,
            max_retries=max_retries,
        )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _messages(request: ProviderRequest) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": request.system_prompt},
            *[
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in request.messages
            ],
        ]

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Groq cevap üretmedi.")

        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Groq boş metin döndürdü.")
        return content.strip()

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.default_model
        payload = {
            "model": model,
            "messages": self._messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }

        last_error: Exception | None = None
        started = time.perf_counter()

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                )

                if response.status_code == 429 and attempt < self.max_retries:
                    retry_after = response.headers.get("retry-after")
                    try:
                        delay = float(retry_after) if retry_after else 1.5
                    except ValueError:
                        delay = 1.5
                    await asyncio.sleep(max(0.5, delay))
                    continue

                response.raise_for_status()
                data = response.json()
                usage = data.get("usage") or {}

                return ProviderResponse(
                    provider=self.name,
                    model=model,
                    content=self._extract_text(data),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    raw_usage=usage,
                    rate_limit={
                        "request_limit": _header_int(
                            response.headers,
                            "x-ratelimit-limit-requests",
                        ),
                        "requests_remaining": _header_int(
                            response.headers,
                            "x-ratelimit-remaining-requests",
                        ),
                        "token_limit": _header_int(
                            response.headers,
                            "x-ratelimit-limit-tokens",
                        ),
                        "tokens_remaining": _header_int(
                            response.headers,
                            "x-ratelimit-remaining-tokens",
                        ),
                        "request_reset": response.headers.get(
                            "x-ratelimit-reset-requests"
                        ),
                        "token_reset": response.headers.get(
                            "x-ratelimit-reset-tokens"
                        ),
                    },
                )
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.75 * (2 ** attempt))

        raise RuntimeError(f"Groq isteği başarısız: {last_error}")

    async def list_models(self) -> list[CatalogModel]:
        response = await self.client.get(
            f"{self.base_url}/models",
            headers=self.headers,
        )
        response.raise_for_status()
        entries = response.json().get("data") or []

        return [
            CatalogModel(
                id=item["id"],
                name=item.get("id"),
                publisher=item.get("owned_by"),
            )
            for item in entries
            if isinstance(item, dict) and item.get("id")
        ]
