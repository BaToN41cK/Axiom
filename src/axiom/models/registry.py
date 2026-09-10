"""Provider registry: creates provider adapters from config."""

from __future__ import annotations

from typing import Any

from axiom.models.ollama import OllamaProvider
from axiom.models.openai_compatible import OpenAICompatibleProvider
from axiom.models.provider import ModelProvider


class ProviderRegistry:
    """Factory for provider adapters by name."""

    def __init__(self, providers_config: dict[str, Any] | None = None) -> None:
        self._config = providers_config or {}

    def create(
        self,
        name: str,
        model: str,
        api_key: str = "",
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> ModelProvider:
        section = dict(self._config.get(name, {}))
        if base_url:
            section["base_url"] = base_url
        if headers:
            section["headers"] = headers
        if name == "ollama":
            return OllamaProvider(
                model=model, base_url=section.get("base_url", "http://localhost:11434")
            )
        if name in ("openai_compatible", "groq", "zai", "bai"):
            return OpenAICompatibleProvider(
                model=model,
                base_url=section.get("base_url", "https://api.groq.com/openai/v1"),
                api_key=api_key,
                headers=section.get("headers") or {},
            )
        raise ValueError(f"Unknown provider type: {name}")

    def known_types(self) -> list[str]:
        return ["openai_compatible", "ollama"]
