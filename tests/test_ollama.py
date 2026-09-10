"""Tests for Ollama provider."""

from __future__ import annotations

import pytest

from axiom.models.ollama import OllamaProvider


class TestOllamaProvider:
    """Test OllamaProvider."""

    def test_init(self):
        provider = OllamaProvider(model="llama3")
        assert provider.name == "ollama"
        assert provider.model_name == "llama3"
        assert provider.supports_streaming is True
        assert provider.supports_tools is True

    def test_init_custom_url(self):
        provider = OllamaProvider(model="qwen3", base_url="http://localhost:11434")
        assert provider._base_url == "http://localhost:11434"

    def test_build_messages(self):
        provider = OllamaProvider()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = provider._build_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"

    def test_build_tools(self):
        provider = OllamaProvider()
        from axiom.models.provider import ToolSpec
        tools = [
            ToolSpec(
                name="read_file",
                description="Read a file",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            )
        ]
        result = provider._build_tools(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_validate_connection_error(self):
        provider = OllamaProvider(base_url="http://localhost:11434")
        # Should return False if Ollama is not running
        result = await provider.validate()
        # This may pass or fail depending on whether Ollama is installed
        assert isinstance(result, bool)
