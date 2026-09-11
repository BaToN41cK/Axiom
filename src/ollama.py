"""Ollama API client for AXIOM."""

import json
from typing import AsyncGenerator, Optional

import httpx

from src.config import config


class OllamaClient:
    """Client for communicating with Ollama API."""

    def __init__(self, host: str = "", model: str = ""):
        self.host = host or config.ollama_host
        self.model = model or config.model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            # trust_env=False prevents system/environment proxies from
            # intercepting requests to the local Ollama server.
            self._client = httpx.AsyncClient(
                base_url=self.host,
                timeout=httpx.Timeout(30.0, read=None),
                trust_env=False,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def list_models(self) -> list[dict]:
        """List available models from Ollama."""
        client = await self._get_client()
        resp = await client.get("/api/tags")
        resp.raise_for_status()
        return resp.json().get("models", [])

    async def pull_model(self, model: str) -> dict:
        """Pull a model from Ollama."""
        client = await self._get_client()
        resp = await client.post("/api/pull", json={"name": model}, timeout=None)
        resp.raise_for_status()
        return resp.json()

    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        options: Optional[dict] = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream chat response from Ollama.
        
        Yields parsed JSON objects from the streaming response.
        """
        client = await self._get_client()

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools

        if options:
            payload["options"] = options

        async with client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        yield data
                    except json.JSONDecodeError:
                        continue

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        options: Optional[dict] = None,
    ) -> dict:
        """Non-streaming chat response from Ollama."""
        client = await self._get_client()

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools

        if options:
            payload["options"] = options

        resp = await client.post("/api/chat", json=payload, timeout=120.0)
        resp.raise_for_status()
        return resp.json()

    async def get_model_info(self, model: str = "") -> dict:
        """Get model information."""
        client = await self._get_client()
        resp = await client.post("/api/show", json={"name": model or self.model})
        resp.raise_for_status()
        return resp.json()
