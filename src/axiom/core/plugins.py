"""Plugin SDK (п.20): manifest + capabilities + install/list/remove."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    capabilities: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    ui: tuple[str, ...] = ()


class PluginRegistry:
    """In-memory реестр + персист имён установленных плагинов."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}

    def install(self, manifest: PluginManifest) -> None:
        self._plugins[manifest.name] = manifest

    def remove(self, name: str) -> bool:
        return self._plugins.pop(name, None) is not None

    def get(self, name: str) -> PluginManifest | None:
        return self._plugins.get(name)

    def list(self) -> list[PluginManifest]:
        return list(self._plugins.values())

    def save(self, path) -> None:
        import json as _json
        from pathlib import Path as _Path
        target = _Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"name": p.name, "version": p.version, "description": p.description,
                    "capabilities": list(p.capabilities), "tools": list(p.tools),
                    "providers": list(p.providers), "skills": list(p.skills),
                    "events": list(p.events), "ui": list(p.ui)} for p in self._plugins.values()]
        target.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path) -> None:
        import json as _json
        from pathlib import Path as _Path
        target = _Path(path)
        if not target.exists():
            self._plugins.clear()
            return
        try:
            raw = _json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(raw, list):
            self._plugins.clear()
            for item in raw:
                if isinstance(item, dict) and item.get("name"):
                    self._plugins[str(item["name"])] = PluginManifest(
                        name=str(item["name"]), version=str(item.get("version") or "0.1.0"),
                        description=str(item.get("description") or ""),
                        capabilities=tuple(item.get("capabilities") or ()),
                        tools=tuple(item.get("tools") or ()),
                        providers=tuple(item.get("providers") or ()),
                        skills=tuple(item.get("skills") or ()),
                        events=tuple(item.get("events") or ()),
                        ui=tuple(item.get("ui") or ()))
