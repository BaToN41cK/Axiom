"""ModelCatalog: единый реестр моделей поверх всех провайдеров."""
from __future__ import annotations

from axiom.core.providers.base import ModelProfile


class ModelCatalog:
    def __init__(self) -> None:
        self._models: list[ModelProfile] = []

    def replace(self, models: list[ModelProfile]) -> None:
        self._models = list(models)

    def add(self, models: list[ModelProfile]) -> None:
        seen = {(m.provider_id, m.id) for m in self._models}
        for m in models:
            if (m.provider_id, m.id) not in seen:
                self._models.append(m)
                seen.add((m.provider_id, m.id))

    def all(self) -> list[ModelProfile]:
        return list(self._models)

    def for_provider(self, provider_id: str) -> list[ModelProfile]:
        return [m for m in self._models if m.provider_id == provider_id]

    def get(self, provider_id: str, model_id: str) -> ModelProfile | None:
        for m in self._models:
            if m.provider_id == provider_id and m.id == model_id:
                return m
        return None

    def find(self, model_id: str) -> ModelProfile | None:
        for m in self._models:
            if m.id == model_id:
                return m
        return None
