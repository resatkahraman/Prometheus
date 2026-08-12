from dataclasses import dataclass

from app.core.config import Settings
from app.providers.registry import ProviderRegistry


@dataclass(frozen=True)
class ModelRoute:
    key: str
    provider: str
    model: str
    label: str
    quality: float
    speed: float
    economy: float
    paid: bool = False
    local: bool = False
    model_class: str = "generation"
    capabilities: tuple[str, ...] = ()
    cost_class: str = "zero_free_quota"


class RouteCatalog:
    def __init__(
        self,
        *,
        settings: Settings,
        registry: ProviderRegistry,
    ) -> None:
        self.settings = settings
        self.registry = registry

    def all(self) -> list[ModelRoute]:
        return [
            ModelRoute(
                key="local_qwen",
                provider="ollama",
                model=self.settings.ollama_model,
                label=f"Local {self.settings.ollama_model}",
                quality=7.0,
                speed=7.0,
                economy=10.0,
                local=True,
                capabilities=("general_generation", "general_chat", "turkish_chat", "summarization", "planning", "local_reasoning", "local_code", "rag_generation"),
                cost_class="zero_local",
            ),
            ModelRoute(
                key="local_expert",
                provider="ollama",
                model=self.settings.ollama_expert_model,
                label=f"Local Expert {self.settings.ollama_expert_model}",
                quality=8.0,
                speed=3.8,
                economy=10.0,
                local=True,
                capabilities=("general_generation", "general_chat", "turkish_chat", "summarization", "planning", "local_reasoning", "local_code", "rag_generation"),
                cost_class="zero_local",
            ),
            ModelRoute(
                key="local_structured",
                provider="ollama",
                model=self.settings.ollama_structured_model,
                label=f"Local Structured {self.settings.ollama_structured_model}",
                quality=7.5,
                speed=7.0,
                economy=10.0,
                local=True,
                model_class="structured_tool",
                capabilities=("structured_output", "json_schema", "intent_classification", "tool_routing"),
                cost_class="zero_local",
            ),
            ModelRoute(
                key="gemini",
                provider="gemini",
                model=self.settings.gemini_model,
                label="Gemini Flash Lite",
                quality=8.1,
                speed=8.2,
                economy=9.5,
            ),
            ModelRoute(
                key="github",
                provider="github",
                model=self.settings.github_model,
                label="GitHub GPT-4.1 Mini",
                quality=9.0,
                speed=7.5,
                economy=9.8,  # Education token = effectively free
            ),
            ModelRoute(
                key="groq_fast",
                provider="groq",
                model=self.settings.groq_fast_model,
                label="Groq Llama 3.1 8B Fast",
                quality=6.6,
                speed=10.0,
                economy=10.0,
            ),
            ModelRoute(
                key="groq_strong",
                provider="groq",
                model=self.settings.groq_strong_model,
                label="Groq Llama 3.3 70B",
                quality=8.4,
                speed=9.2,
                economy=9.0,
            ),
        ]

    def get(self, route_key: str) -> ModelRoute:
        normalized = route_key.strip().lower()
        for route in self.all():
            if route.key == normalized:
                return route
        raise ValueError(f"Bilinmeyen route: {route_key}")

    def is_enabled(self, route: ModelRoute) -> bool:
        if route.key == "github" and not self.settings.github_route_enabled:
            return False
        if route.local and not self.settings.local_model_enabled:
            return False
        if route.paid and not self.settings.effective_paid_models_enabled:
            return False
        return self.registry.get_optional(route.provider) is not None

    def disabled_reason(self, route: ModelRoute) -> str | None:
        if route.key == "github" and not self.settings.github_route_enabled:
            return "GitHub Models endpoint'i 410 döndürdüğü için rota geçici olarak devre dışı."
        if route.local and not self.settings.local_model_enabled:
            return "Yerel model yapılandırmada devre dışı."
        if route.paid and self.settings.free_only_mode:
            return "Free-only kilidi ücretli rotayı devre dışı bıraktı."
        if route.paid and not self.settings.paid_models_enabled:
            return "Ücretli modeller kullanıcı tarafından etkinleştirilmedi."
        if route.paid and self.settings.monthly_paid_budget_usd <= 0:
            return "Aylık ücretli model bütçesi 0."
        if self.registry.get_optional(route.provider) is None:
            return "API anahtarı olmadığı için devre dışı."
        return None

    def enabled(self) -> list[ModelRoute]:
        return [route for route in self.all() if self.is_enabled(route)]
