"""AXIOM configuration — loads from environment variables."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Application configuration."""

    # Ollama
    ollama_host: str = ""
    model: str = ""

    # Features
    web_enabled: bool = True
    reasoning_enabled: bool = True

    # Future features (disabled)
    files_enabled: bool = False
    terminal_enabled: bool = False
    memory_enabled: bool = False
    pc_control_enabled: bool = False

    # Model context window (tokens) — used for context %
    context_window: int = 32768

    # Display
    max_sources_display: int = 10
    web_fetch_timeout: int = 15
    web_search_results: int = 8

    # Disabled tools for future use
    disabled_tools: list = field(default_factory=lambda: [
        "files", "terminal", "memory", "pc", "browser"
    ])


def load_config() -> Config:
    """Load configuration from environment."""
    return Config(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
        model=os.getenv("AXIOM_MODEL", "qwen3:8b"),
        web_enabled=os.getenv("AXIOM_WEB_ENABLED", "true").lower() == "true",
        reasoning_enabled=os.getenv("AXIOM_REASONING_ENABLED", "true").lower() == "true",
        context_window=int(os.getenv("AXIOM_CONTEXT_WINDOW", "32768")),
    )


config = load_config()
