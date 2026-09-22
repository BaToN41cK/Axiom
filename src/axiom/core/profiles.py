"""Profile / Persona Manager — system prompt library stored as profiles.

Profiles are stored in ``~/.axiom/profiles.json`` and can be selected,
created, edited, and deleted at runtime.
"""

from __future__ import annotations

import json

from axiom.core.config import axiom_home
from axiom.core.logging import get_logger

_LOG = get_logger("profiles")

_PROFILES_PATH = axiom_home() / "profiles.json"

#: Built-in profile that ships with AXIOM.
DEFAULT_PROFILES: dict[str, str] = {
    "Default": (
        "You are AXIOM, a precise local AI assistant running on the user's machine "
        "through Ollama. Answer directly and accurately. Use markdown when it helps. "
        "Never invent facts; if you are unsure, say so."
    ),
    "Programmer": (
        "You are AXIOM, an expert programming assistant. Help the user write, "
        "debug, and improve code. Provide concise explanations with code examples. "
        "Prefer practical solutions over theoretical discussions. When suggesting "
        "changes, show the diff or the relevant code block."
    ),
    "Translator": (
        "You are AXIOM, a professional translator. Translate the user's text "
        "accurately while preserving tone, style, and cultural nuances. When asked, "
        "provide alternative translations and explain your choices."
    ),
    "Writer": (
        "You are AXIOM, a skilled writing assistant. Help the user craft, edit, "
        "and refine their writing. Offer suggestions for structure, style, and "
        "clarity. Adapt your tone to match the user's needs."
    ),
    "Researcher": (
        "You are AXIOM, a thorough research assistant. Provide well-structured, "
        "factual answers with citations where possible. Analyse topics critically "
        "and present multiple perspectives when relevant. Use web search proactively."
    ),
}


class ProfileManager:
    """Manages system prompt profiles with persistence."""

    def __init__(self) -> None:
        self._profiles: dict[str, str] = {}
        self._active: str = "Default"
        self._load()

    # ------------------------------------------------------------------ public

    @property
    def active_name(self) -> str:
        return self._active

    @property
    def active_prompt(self) -> str:
        return self._profiles.get(self._active, DEFAULT_PROFILES.get("Default", ""))

    @property
    def names(self) -> list[str]:
        return list(self._profiles.keys())

    @property
    def all(self) -> dict[str, str]:
        return dict(self._profiles)

    def select(self, name: str) -> bool:
        """Select a profile by name. Returns True on success."""
        if name in self._profiles:
            self._active = name
            _LOG.info("Selected profile: %s", name)
            self._save()
            return True
        return False

    def get(self, name: str) -> str | None:
        return self._profiles.get(name)

    def add(self, name: str, prompt: str) -> bool:
        """Add or update a profile."""
        cleaned = name.strip()
        if not cleaned:
            return False
        self._profiles[cleaned] = prompt.strip()
        _LOG.info("Profile added/updated: %s", cleaned)
        self._save()
        return True

    def remove(self, name: str) -> bool:
        """Remove a profile. Returns True on success."""
        if name not in self._profiles:
            return False
        if name == self._active:
            self._active = "Default"
        del self._profiles[name]
        _LOG.info("Profile removed: %s", name)
        self._save()
        return True

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename a profile."""
        if old_name not in self._profiles or not new_name.strip():
            return False
        prompt = self._profiles.pop(old_name)
        self._profiles[new_name.strip()] = prompt
        if self._active == old_name:
            self._active = new_name.strip()
        self._save()
        _LOG.info("Profile renamed: %s -> %s", old_name, new_name)
        return True

    # ----------------------------------------------------------------- private

    def _load(self) -> None:
        """Load profiles from disk, merging with defaults."""
        merged = dict(DEFAULT_PROFILES)
        if _PROFILES_PATH.exists():
            try:
                raw = json.loads(_PROFILES_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for key, value in raw.items():
                        if isinstance(key, str) and isinstance(value, str):
                            merged[key] = value
            except (OSError, json.JSONDecodeError) as exc:
                _LOG.warning("Could not load profiles: %s", exc)
        self._profiles = merged
        self._active = "Default"
        _LOG.info("Loaded %d profiles", len(self._profiles))

    def _save(self) -> None:
        try:
            _PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
            _PROFILES_PATH.write_text(
                json.dumps(self._profiles, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            _LOG.warning("Could not save profiles: %s", exc)

    def reset(self) -> None:
        """Reset all profiles to defaults."""
        self._profiles = dict(DEFAULT_PROFILES)
        self._active = "Default"
        self._save()
        _LOG.info("Profiles reset to defaults")
