"""ModelManager: providers, models, current model selection."""

from __future__ import annotations

from typing import Any

from axiom.config.defaults import DEFAULT_CONFIG
from axiom.core.errors import ModelNotFoundError
from axiom.core.types import HealthStatus
from axiom.models.ollama import OllamaProvider
from axiom.models.openai_compatible import OpenAICompatibleProvider
from axiom.models.provider import ModelInfo, ProviderInfo

# Metadata for well-known models; availability checked at runtime.
KNOWN_MODELS: dict[str, dict[str, Any]] = {
    "GPT-OSS-120B": dict(context_window=131072, max_output_tokens=16384, reasoning=True,
                         speed=80, priority=100, task_types=("CODING", "REVIEW")),
    "GPT-OSS-20B": dict(context_window=131072, max_output_tokens=8192, reasoning=True,
                        speed=150, priority=60, task_types=("FAST", "CODING")),
    "GLM-5.3-Flash": dict(context_window=131072, speed=180, priority=70,
                          task_types=("FAST", "REVIEW", "FALLBACK")),
    "GLM-4.7-Flash": dict(context_window=131072, speed=180, priority=40,
                          task_types=("FAST", "FALLBACK")),
    "GLM-4.6V-Flash": dict(context_window=65536, vision=True, speed=140, priority=35,
                           task_types=("VISION", "FALLBACK")),
    "GLM-4.5-Flash": dict(context_window=131072, speed=200, priority=30,
                          task_types=("FAST", "FALLBACK")),
    "MiMo-V2.5": dict(context_window=131072, reasoning=True, speed=90, priority=80,
                      task_types=("REASONING", "ORCHESTRATOR", "FALLBACK")),
    "Qwen3.8-Flash": dict(context_window=131072, speed=200, priority=45,
                          task_types=("FAST", "FALLBACK")),
    "Qwen3.6-27B": dict(context_window=131072, speed=170, priority=55, task_types=("FAST",)),
    "Command A+": dict(context_window=131072, speed=110, priority=35, task_types=("FALLBACK",)),
    "Mistral Medium": dict(context_window=131072, speed=120, priority=35, task_types=("FALLBACK",)),
    "Mistral Small": dict(context_window=65536, speed=160, priority=25,
                          task_types=("FAST", "FALLBACK")),
    "Codestral": dict(context_window=65536, speed=170, priority=35,
                      task_types=("CODING", "FALLBACK")),
}


class ModelManager:
    """Central model/provider management."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = config or dict(DEFAULT_CONFIG)
        self._providers: dict[str, ProviderInfo] = {
            "openai_compatible": ProviderInfo(
                name="openai_compatible", display_name="OpenAI Compatible", requires_api_key=True
            ),
            "ollama": ProviderInfo(
                name="ollama", display_name="Ollama", base_url="http://localhost:11434",
                requires_api_key=False,
            ),
        }

    def list_providers(self) -> list[ProviderInfo]:
        return list(self._providers.values())

    def get_provider(self, name: str) -> ProviderInfo | None:
        return self._providers.get(name)

    def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        models = []
        for model_id, meta in KNOWN_MODELS.items():
            if provider and meta.get("provider", "openai_compatible") != provider:
                continue
            models.append(
                ModelInfo(
                    id=model_id, provider=meta.get("provider", "openai_compatible"),
                    context_window=meta.get("context_window", 32768),
                    max_output_tokens=meta.get("max_output_tokens", 4096),
                    reasoning=meta.get("reasoning", False), vision=meta.get("vision", False),
                    speed=meta.get("speed", 1.0), priority=meta.get("priority", 50),
                    task_types=meta.get("task_types", ()),
                )
            )
        return models

    def get_model(self, model_id: str) -> ModelInfo | None:
        for model in self.list_models():
            if model.id.lower() == model_id.lower():
                return model
        return None

    def get_current_model(self) -> ModelInfo | None:
        model_id = self._config.get("model", {}).get("model", "GPT-OSS-120B")
        model = self.get_model(model_id)
        if model is not None:
            return model
        return ModelInfo(
            id=model_id,
            provider=self._config.get("model", {}).get("provider", "openai_compatible"),
        )

    def create_provider(
        self, provider_name: str, model: str, api_key: str = "",
        provider_config: dict[str, Any] | None = None,
    ):
        """Instantiate a concrete provider adapter."""
        if provider_name == "ollama":
            section = self._config.get("providers", {}).get("ollama", {})
            base = (provider_config or section or {}).get("base_url", "http://localhost:11434")
            return OllamaProvider(model=model, base_url=base)
        if provider_name == "openai_compatible":
            section = dict(self._config.get("providers", {}).get("openai_compatible", {}))
            section.update(provider_config or {})
            return OpenAICompatibleProvider(
                model=model,
                base_url=section.get("base_url", "https://api.groq.com/openai/v1"),
                api_key=api_key,
                headers=section.get("headers") or {},
            )
        raise ModelNotFoundError(f"Unknown provider: {provider_name}")

    async def check_provider_health(self, name: str) -> str:
        """Return provider health ('healthy'/'offline'/...)."""
        provider = self.get_provider(name)
        if provider is None:
            return "unknown"
        current = self.get_current_model()
        instance = self.create_provider(name, model=current.id if current else "")
        ok = await instance.validate()
        provider.health = HealthStatus.HEALTHY if ok else HealthStatus.OFFLINE
        return provider.health.value

    async def list_ollama_models(self) -> list[str]:
        models = await OllamaProvider().list_models()
        provider = self.get_provider("ollama")
        if provider is not None:
            provider.models = models
        return models
