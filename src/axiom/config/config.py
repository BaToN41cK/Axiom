"""Configuration system.

Layered configuration:
    defaults -> global (~/.axiom/config.json) -> project (.axiom/config.json)
    -> environment overrides (AXIOM_<SECTION>__<KEY> or specific aliases)
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from axiom.config.defaults import DEFAULT_CONFIG, DEFAULT_PERMISSIONS
from axiom.core.logging import get_logger

logger = get_logger("config")

_ALIASES: dict[str, tuple[str, str]] = {
    "AXIOM_MODEL": ("model", "model"),
    "AXIOM_PROVIDER": ("model", "provider"),
    "AXIOM_BASE_URL": ("providers", "openai_compatible:base_url"),
    "AXIOM_TEMPERATURE": ("model", "temperature"),
}


def global_config_dir() -> Path:
    """Global config dir: ~/.axiom."""
    return Path.home() / ".axiom"


def project_config_dir(workspace: Path | None = None) -> Path:
    """Project config dir: <workspace>/.axiom."""
    ws = workspace or Path.cwd()
    return ws / ".axiom"


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read config %s: %s", path, exc)
        return {}


class Config:
    """Layered configuration container."""

    def __init__(self, workspace: Path | None = None, data: dict | None = None) -> None:
        self._workspace = workspace or Path.cwd()
        self._data: dict = copy.deepcopy(DEFAULT_CONFIG)
        self._load_layers()
        if data:
            self._data = _deep_merge(self._data, data)

    # -- loading ---------------------------------------------------------
    def _load_layers(self) -> None:
        global_file = global_config_dir() / "config.json"
        project_file = project_config_dir(self._workspace) / "config.json"
        if global_file != project_file:
            self._data = _deep_merge(self._data, _read_json(global_file))
        self._data = _deep_merge(self._data, _read_json(project_file))
        self._apply_env()

    def _apply_env(self) -> None:
        for env_name, (section, dotted_key) in _ALIASES.items():
            value = os.environ.get(env_name)
            if value is None or value == "":
                continue
            parts = dotted_key.split(":")
            keys = [section, *parts]
            self._set_path(keys, self._coerce(value))
        # Generic AXIOM_SECTION__KEY overrides
        for env_name, value in os.environ.items():
            if env_name.startswith("AXIOM_") and "__" in env_name:
                _, section, key = env_name.split("__", 2)
                self._set_path([section.lower(), *key.lower().split("__")], self._coerce(value))

    @staticmethod
    def _coerce(value: str) -> Any:
        lowered = value.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value

    # -- access ----------------------------------------------------------
    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self._data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def set(self, *keys: str, value: Any = None) -> None:
        """Set a nested value.

        Supports both set("a", "b", value=v) and set("a", "b", v) styles.
        """
        if not keys:
            return
        if value is None and len(keys) >= 2 and keys[-1] != "value":
            value = keys[-1]
            keys = keys[:-1]
        self._set_path(list(keys), value)

    def _set_path(self, keys: list[str], value: Any) -> None:
        node = self._data
        for key in keys[:-1]:
            if key not in node or not isinstance(node[key], dict):
                node[key] = {}
            node = node[key]
        node[keys[-1]] = value

    def to_dict(self) -> dict:
        return copy.deepcopy(self._data)

    # -- secrets ---------------------------------------------------------
    def get_api_key(self, provider: str = "openai_compatible") -> str:
        """Return API key from env only; never stored to disk in plaintext by us."""
        env_name = self.get("providers", provider, "api_key_env", default="AXIOM_API_KEY")
        if provider == "ollama":
            return ""
        key = os.environ.get(env_name, "")
        if key:
            return key
        generic = os.environ.get("AXIOM_API_KEY", "")
        return generic

    # -- permissions -----------------------------------------------------
    @property
    def permissions(self) -> dict[str, str]:
        return dict(self.get("permissions", default=dict(DEFAULT_PERMISSIONS)))

    @property
    def model_config(self) -> dict:
        return dict(self.get("model", default={}))

    @property
    def workspace(self) -> Path:
        return self._workspace

    # -- persistence -----------------------------------------------------
    def save(self, scope: str = "global") -> Path:
        if scope == "project":
            path = project_config_dir(self._workspace) / "config.json"
        else:
            path = global_config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Strip secrets: we never write api keys.
        data = copy.deepcopy(self._data)
        data.get("providers", {}).pop("api_key", None)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
