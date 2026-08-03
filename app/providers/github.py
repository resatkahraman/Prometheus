import asyncio
import time
from typing import Any

import httpx

from app.core.schemas import CatalogModel
from app.providers.base import AIProvider, ProviderRequest, ProviderResponse


class GitHubModelsProvider(AIProvider):
    name = "github"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        token: str,
        base_url: str,
        api_version: str,
        default_model: str,
        max_retries: int,
    ) -> None:
        super().__init__(
            client=client,
            default_model=default_model,
            max_retries=max_retries,
        )
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": self.api_version,
            "Content-Type": "application/json",
        }

    def _messages(self, request: ProviderRequest) -> list[dict[str, str]]:
        messages = [
            {"role": "system", "content": request.system_prompt}
        ]
        messages.extend(
            {
                "role": message.role,
                "content": message.content,
            }
            for message in request.messages
        )
        return messages

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("GitHub Models cevap üretmedi.")

        content = choices[0].get("message", {}).get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            text = "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
            ).strip()
            if text:
                return text

        raise RuntimeError("GitHub Models boş metin döndürdü.")

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.default_model
        url = f"{self.base_url}/inference/chat/completions"
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
                    url,
                    headers=self.headers,
                    json=payload,
                )

                if response.status_code == 429 and attempt < self.max_retries:
                    await asyncio.sleep(1.5 * (2 ** attempt))
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
                )
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.75 * (2 ** attempt))

        raise RuntimeError(f"GitHub Models isteği başarısız: {last_error}")

    async def list_models(self) -> list[CatalogModel]:
        response = await self.client.get(
            f"{self.base_url}/catalog/models",
            headers=self.headers,
        )
        response.raise_for_status()
        data = response.json()

        entries = (
            data.get("models") or data.get("value") or []
            if isinstance(data, dict)
            else data
        )

        models: list[CatalogModel] = []
        for item in entries:
            if not isinstance(item, dict) or not item.get("id"):
                continue

            publisher = item.get("publisher")
            if isinstance(publisher, dict):
                publisher = publisher.get("name") or publisher.get("id")

            limits = item.get("limits") or {}
            models.append(
                CatalogModel(
                    id=item["id"],
                    name=item.get("name") or item.get("display_name"),
                    publisher=publisher,
                    rate_limit_tier=(
                        limits.get("tier")
                        if isinstance(limits, dict)
                        else None
                    ),
                )
            )

        return models
