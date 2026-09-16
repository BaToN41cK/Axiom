"""AXIOM configuration — loading, validation and persistence.

First run must work with zero manual setup: defaults point at a local Ollama
instance and the model is auto-discovered by :mod:`axiom.core.models`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def axiom_home() -> Path:
    """Root of AXIOM's local data (``AXIOM_HOME`` overrides the default)."""
    override = os.environ.get("AXIOM_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".axiom"


class Config(BaseModel):
    """Persisted user configuration."""

    ollama_url: str = DEFAULT_OLLAMA_URL
    model: str | None = None
    #: None = automatic (follow model capability), True/False = explicit request
    think: bool | None = None
    #: Enable the web-search capability (search still only runs when needed)
    web_search_enabled: bool = True
    #: How many search sources to keep / how many pages to actually read
    search_max_sources: int = Field(default=5, ge=1, le=10)
    search_read_sources: int = Field(default=3, ge=0, le=10)
    #: Show real reasoning when the model provides it
    show_reasoning: bool = True
    #: Whether the reasoning block starts expanded
    reasoning_expanded: bool = False
    #: UI theme name ("obsidian" is the built-in AXIOM palette)
    theme: str = "obsidian"
    #: Subtle animations (spinners, splash, transitions)
    animations: bool = True
    #: Persist conversations between runs
    save_history: bool = True
    #: Optional generation parameters
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    system_prompt: str | None = None

    @classmethod
    def path(cls) -> Path:
        return axiom_home() / "config.json"

    @classmethod
    def load(cls) -> Config:
        """Load configuration, falling back to defaults on any problem.

        A corrupt or unreadable config file must never crash the application.
        """
        config_path = cls.path()
        if not config_path.exists():
            config = cls()
            config.save()
            return config
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        try:
            return cls.model_validate(raw)
        except ValidationError:
            # keep only the fields that are still valid, ignore the rest
            valid: dict[str, object] = {}
            for name in cls.model_fields:
                if name in raw:
                    try:
                        cls.model_validate({name: raw[name]})
                    except ValidationError:
                        continue
                    valid[name] = raw[name]
            try:
                return cls.model_validate(valid)
            except ValidationError:
                return cls()

    def save(self) -> None:
        """Persist configuration atomically."""
        config_path = self.path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = config_path.with_suffix(".json.tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(config_path)
