import httpx

from app.core.config import Settings
from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.github import GitHubModelsProvider
from app.providers.groq import GroqProvider
from app.providers.ollama import OllamaProvider


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        provider_retries = (
            min(
                settings.max_retries,
                settings.free_provider_max_retries,
            )
            if settings.free_only_mode
            else settings.max_retries
        )
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            limits=httpx.Limits(
                max_connections=30,
                max_keepalive_connections=15,
            ),
        )
        self._providers: dict[str, AIProvider] = {}

        if settings.local_model_enabled:
            self._providers["ollama"] = OllamaProvider(
                client=self.client,
                base_url=settings.ollama_base_url,
                default_model=settings.ollama_model,
                context_tokens=settings.ollama_context_tokens,
                keep_alive=settings.ollama_keep_alive,
                timeout_seconds=settings.local_model_timeout_seconds,
                expert_model=settings.ollama_expert_model,
                expert_timeout_seconds=settings.local_expert_timeout_seconds,
                managed_models=(
                    settings.ollama_model,
                    settings.ollama_expert_model,
                    settings.ollama_structured_model,
                    settings.ollama_embedding_model,
                ),
            )

        if settings.gemini_api_key:
            self._providers["gemini"] = GeminiProvider(
                client=self.client,
                api_key=settings.gemini_api_key,
                base_url=settings.gemini_base_url,
                default_model=settings.gemini_model,
                max_retries=provider_retries,
            )

        if settings.github_token:
            self._providers["github"] = GitHubModelsProvider(
                client=self.client,
                token=settings.github_token,
                base_url=settings.github_base_url,
                api_version=settings.github_api_version,
                default_model=settings.github_model,
                max_retries=provider_retries,
            )

        if settings.groq_api_key:
            self._providers["groq"] = GroqProvider(
                client=self.client,
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                default_model=settings.groq_fast_model,
                max_retries=provider_retries,
            )

    def provider_slots(self) -> dict[str, AIProvider | None]:
        return {
            "ollama": self._providers.get("ollama"),
            "gemini": self._providers.get("gemini"),
            "github": self._providers.get("github"),
            "groq": self._providers.get("groq"),
        }

    def names(self) -> list[str]:
        return list(self._providers)

    def get(self, name: str) -> AIProvider:
        normalized = name.strip().lower()
        provider = self._providers.get(normalized)
        if provider is None:
            raise ValueError(
                f"'{normalized}' sağlayıcısı etkin değil veya tanımsız."
            )
        return provider

    def get_optional(self, name: str):
        return self._providers.get(name.strip().lower())

    async def close(self) -> None:
        await self.client.aclose()
