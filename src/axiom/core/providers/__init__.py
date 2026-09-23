"""Provider Abstraction Layer — единый слой AXIOM → Provider → Model.

Не писать отдельную логику агента под каждого провайдера: агент
работает только против :class:`Provider`, а каждый вендор — это адаптер.
"""

from axiom.core.providers.anthropic import AnthropicProvider
from axiom.core.providers.base import (
    ChatMessage,
    ChatResult,
    ModelProfile,
    Provider,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderError,
    ProviderStatus,
    ProviderUnavailableError,
    StreamChunk,
    ToolCall,
    Usage,
)
from axiom.core.providers.catalog import ModelCatalog
from axiom.core.providers.known import KNOWN_PROVIDERS, KnownProvider, known_provider_ids
from axiom.core.providers.manager import ProviderConfig, ProviderManager
from axiom.core.providers.ollama_provider import OllamaProvider
from axiom.core.providers.openai_compat import OpenAICompatibleProvider

__all__ = [
    "KNOWN_PROVIDERS",
    "AnthropicProvider",
    "ChatMessage",
    "ChatResult",
    "KnownProvider",
    "ModelCatalog",
    "ModelProfile",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "Provider",
    "ProviderAuthError",
    "ProviderCapabilities",
    "ProviderConfig",
    "ProviderError",
    "ProviderManager",
    "ProviderStatus",
    "ProviderUnavailableError",
    "StreamChunk",
    "ToolCall",
    "Usage",
    "known_provider_ids",
]
