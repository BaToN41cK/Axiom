"""Ollama provider: local model discovery, chat and streaming."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from axiom.core.logging import get_logger
from axiom.models.openai_compatible import OpenAICompatibleProvider, raise_for_status
from axiom.models.provider import ChatResponse, StreamChunk, ToolSpec, Usage
from axiom.models.streaming import ToolCallAccumulator

logger = get_logger("ollama")

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(OpenAICompatibleProvider):
    """Provider for a local Ollama server.

    Uses Ollama's OpenAI-compatible endpoints (/v1/chat/completions)
    plus native /api/tags for model discovery.
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(model=model, base_url=base_url, api_key="", timeout=timeout)
        self._base_url = base_url.rstrip("/")

    # -- discovery ---------------------------------------------------------
    async def list_models(self) -> list[str]:
        """Return locally installed Ollama models (empty if Ollama is down)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
            if response.status_code != 200:
                logger.debug("Ollama tags returned HTTP %s", response.status_code)
                return []
            data = response.json()
            return [m.get("name", "") for m in data.get("models", [])]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.debug("Ollama list_models failed: %s", exc)
            return []

    async def validate(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
