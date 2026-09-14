"""Model discovery and capability detection.

Capabilities are taken from Ollama's own ``/api/tags`` response
(the live server reports e.g. ``["completion","tools","thinking","vision"]``).
When a capability is absent from the response it is reported as ``unknown`` —
never optimistically as supported.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from axiom.core.config import Config
from axiom.core.ollama import OllamaClient

_KNOWN_CAPABILITIES = ("completion", "tools", "thinking", "vision")


class ModelInfo(BaseModel):
    """A model available on the Ollama server."""

    name: str
    size: int = 0
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""
    context_length: int | None = None
    #: raw capability names reported by Ollama (may be empty)
    capabilities: list[str] = Field(default_factory=list)

    def supports(self, capability: str) -> bool | None:
        """True/False when Ollama reports it, ``None`` when unknown."""
        if not self.capabilities:
            return None
        if capability in self.capabilities:
            return True
        # Ollama lists the full capability set for a model; a known capability
        # that is absent is therefore genuinely unsupported.
        if capability in _KNOWN_CAPABILITIES:
            return False
        return None

    @property
    def display_name(self) -> str:
        """A compact human-friendly label, e.g. ``Qwen3 8B``."""
        base, _, tag = self.name.partition(":")
        base = base.split("/")[-1].replace("_", " ").replace("-", " ").strip()
        words = [w.upper() if len(w) <= 3 and w.isalpha() else w.capitalize() for w in base.split()]
        label = " ".join(words) if words else self.name
        if tag and tag != "latest" and not self.parameter_size:
            label = f"{label} {tag}"
        elif self.parameter_size:
            label = f"{label} {self.parameter_size}"
        return label

    @property
    def size_gb(self) -> float:
        return round(self.size / (1024 ** 3), 2)


class ModelRegistry:
    """Discovers models and resolves the active one."""

    def __init__(self, client: OllamaClient) -> None:
        self._client = client
        self._models: list[ModelInfo] = []

    @property
    def models(self) -> list[ModelInfo]:
        return list(self._models)

    async def refresh(self) -> list[ModelInfo]:
        """Re-read the model list from Ollama."""
        raw_models = await self._client.list_models()
        models: list[ModelInfo] = []
        for item in raw_models:
            name = item.get("name") or item.get("model")
            if not name:
                continue
            details = item.get("details") or {}
            caps = item.get("capabilities")
            context_length = None
            if isinstance(details, dict):
                raw_ctx = details.get("context_length")
                if isinstance(raw_ctx, int):
                    context_length = raw_ctx
            models.append(
                ModelInfo(
                    name=str(name),
                    size=int(item.get("size") or 0),
                    parameter_size=str(details.get("parameter_size") or "") if isinstance(details, dict) else "",
                    quantization=str(details.get("quantization_level") or "") if isinstance(details, dict) else "",
                    family=str(details.get("family") or "") if isinstance(details, dict) else "",
                    context_length=context_length,
                    capabilities=[str(c) for c in caps] if isinstance(caps, list) else [],
                )
            )
        models.sort(key=lambda m: m.name.lower())
        self._models = models
        return list(models)

    def get(self, name: str) -> ModelInfo | None:
        for model in self._models:
            if model.name == name:
                return model
        return None

    def resolve(self, preferred: str | None) -> ModelInfo | None:
        """Pick the configured model, else the first available one."""
        if preferred:
            found = self.get(preferred)
            if found is not None:
                return found
        return self._models[0] if self._models else None

    @staticmethod
    def persist_selection(config: Config, model_name: str) -> None:
        """Store the active model in the configuration file."""
        if config.model != model_name:
            config.model = model_name
            config.save()
