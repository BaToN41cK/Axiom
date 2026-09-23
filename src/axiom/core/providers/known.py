"""Зашитые дефолты известных провайдеров: endpoint + env для ключа."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnownProvider:
    id: str
    label: str
    base_url: str
    api_key_env: tuple[str, ...] = ()
    model_api: str = "openai-chat"  # openai-chat | openai-responses | anthropic | ollama
    default_models: tuple[str, ...] = ()
    docs: str = ""


KNOWN_PROVIDERS: tuple[KnownProvider, ...] = (
    KnownProvider("anthropic", "Anthropic", "https://api.anthropic.com",
                  ("ANTHROPIC_API_KEY",), "anthropic",
                  ("claude-opus-4-6", "claude-sonnet-4-6")),
    KnownProvider("openai", "OpenAI", "https://api.openai.com/v1", ("OPENAI_API_KEY",),
                  "openai-responses", ("gpt-5.2", "gpt-5-mini")),
    KnownProvider("openai_compatible", "OpenAI Compatible", "", ("OPENAI_COMPATIBLE_API_KEY",),
                  "openai-chat", ()),
    KnownProvider("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                  ("GOOGLE_API_KEY", "GEMINI_API_KEY"), "openai-chat",
                  ("gemini-3-pro-preview", "gemini-2.5-flash")),
    KnownProvider("deepseek", "DeepSeek", "https://api.deepseek.com/v1", ("DEEPSEEK_API_KEY",),
                  "openai-chat", ("deepseek-chat", "deepseek-reasoner")),
    KnownProvider("xai", "xAI", "https://api.x.ai/v1", ("XAI_API_KEY",),
                  "openai-chat", ("grok-4", "grok-code-fast-1")),
    KnownProvider("mistral", "Mistral", "https://api.mistral.ai/v1", ("MISTRAL_API_KEY",),
                  "openai-chat", ("mistral-large-latest", "codestral-latest")),
    KnownProvider("qwen", "Qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                  ("QWEN_API_KEY", "DASHSCOPE_API_KEY"), "openai-chat",
                  ("qwen3-max", "qwen3-coder-plus")),
    KnownProvider("zai", "Z.AI / GLM", "https://api.z.ai/api/paas/v4", ("ZAI_API_KEY", "ZHIPU_API_KEY"),
                  "openai-chat", ("glm-4.6", "glm-4.5-air")),
    KnownProvider("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",),
                  "openai-chat", ("anthropic/claude-opus-4-6", "openai/gpt-5.2")),
    KnownProvider("together", "Together", "https://api.together.xyz/v1", ("TOGETHER_API_KEY",),
                  "openai-chat", ("deepseek-ai/DeepSeek-V3.1",)),
    KnownProvider("fireworks", "Fireworks", "https://api.fireworks.ai/inference/v1",
                  ("FIREWORKS_API_KEY",), "openai-chat", ("accounts/fireworks/models/glm-4p6",)),
    KnownProvider("groq", "Groq", "https://api.groq.com/openai/v1", ("GROQ_API_KEY",),
                  "openai-chat", ("openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905")),
    KnownProvider("cerebras", "Cerebras", "https://api.cerebras.ai/v1", ("CEREBRAS_API_KEY",),
                  "openai-chat", ("gpt-oss-120b", "qwen-3-235b-a22b-instruct-2507")),
    KnownProvider("ollama", "Ollama", "http://127.0.0.1:11434", (), "ollama", ()),
)


def known_provider_ids() -> list[str]:
    return [p.id for p in KNOWN_PROVIDERS]


def find_known(provider_id: str) -> KnownProvider | None:
    for item in KNOWN_PROVIDERS:
        if item.id == provider_id:
            return item
    return None
