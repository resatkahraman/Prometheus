import asyncio
import time
from typing import Any

import httpx

from app.providers.base import AIProvider, ProviderRequest, ProviderResponse


class GeminiProvider(AIProvider):
    name = "gemini"

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

    def _payload(self, request: ProviderRequest) -> dict[str, Any]:
        role_map = {"user": "user", "assistant": "model"}
        contents: list[dict[str, Any]] = []
        system_parts = [request.system_prompt]

        for message in request.messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue

            contents.append(
                {
                    "role": role_map[message.role],
                    "parts": [{"text": message.content}],
                }
            )

        return {
            "system_instruction": {
                "parts": [{"text": "\n\n".join(system_parts)}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_output_tokens,
            },
        }

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback") or {}
            raise RuntimeError(
                f"Gemini cevap üretmedi. promptFeedback={feedback}"
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict)
        ).strip()

        if not text:
            raise RuntimeError("Gemini boş metin döndürdü.")
        return text

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.default_model
        url = f"{self.base_url}/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        started = time.perf_counter()

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(
                    url,
                    headers=headers,
                    json=self._payload(request),
                )

                if response.status_code == 429 and attempt < self.max_retries:
                    await asyncio.sleep(1.5 * (2 ** attempt))
                    continue

                response.raise_for_status()
                data = response.json()
                usage = data.get("usageMetadata") or {}

                return ProviderResponse(
                    provider=self.name,
                    model=model,
                    content=self._extract_text(data),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    input_tokens=usage.get("promptTokenCount"),
                    output_tokens=usage.get("candidatesTokenCount"),
                    raw_usage=usage,
                )
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.75 * (2 ** attempt))

        raise RuntimeError(f"Gemini isteği başarısız: {last_error}")
