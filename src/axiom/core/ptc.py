"""Code / PTC mode (п.21): модель пишет мини-программу тулов, Core исполняет.

Вместо раундов model→tool→model модель отдаёт один JSON-программный блок:

    ```axiom-program
    [{"tool": "read_file", "args": {"path": "app.py"}},
     {"tool": "run_command", "args": {"command": "pytest -q"}}]
    ```

Ядро исполняет шаги последовательно через ToolRegistry + Sandbox и
возвращает сводку одной пачкой — меньше round-trips и токенов.
"""
from __future__ import annotations

import json
import re

from axiom.core.tools.base import ToolPermission, ToolResult
from axiom.core.tools.registry import ToolRegistry

_FENCE = re.compile(r"```axiom-program\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_MAX_STEPS = 24


def parse_program(text: str) -> list[dict]:
    """Достать программу шагов из ответа модели. Пустой список = не PTC."""
    match = _FENCE.search(text or "")
    if not match:
        return []
    raw = match.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    steps: list[dict] = []
    for item in data[:_MAX_STEPS]:
        if isinstance(item, dict) and item.get("tool"):
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            steps.append({"tool": str(item["tool"]), "args": args})
    return steps


async def run_program(steps: list[dict], registry: ToolRegistry,
                      *, sandbox=None, permissions=None, trajectory=None,
                      allowed_tools: set[str] | None = None) -> dict:
    """Execute PTC steps through sandbox and permission policy before registry."""
    if permissions is None:
        from axiom.core.permissions import PermissionManager

        permissions = PermissionManager()

    results: list[dict] = []
    ok_all = True
    for step in steps:
        if not isinstance(step, dict):
            continue
        tool = str(step.get("tool") or "")
        args = dict(step.get("args") or {}) if isinstance(step.get("args"), dict) else {}
        definition = registry.get(tool)
        error: str | None = None
        approved = False

        if allowed_tools is not None and tool not in allowed_tools:
            error = f"Blocked by preset tool policy: {tool} is not allowed."
        elif definition is None:
            error = f"Unknown tool: {tool}"
        elif definition.permission is ToolPermission.NEVER:
            error = f"Tool '{tool}' is disabled"
        else:
            tool_permission = definition.permission
            try:
                classifier = registry.classifier.get(tool)
                if classifier is not None:
                    tool_permission = classifier(tool, args)
                sandbox_policy = sandbox.decide(tool) if sandbox is not None else "auto"
            except Exception as exc:
                error = f"Permission check failed for {tool}: {type(exc).__name__}: {exc}"
                sandbox_policy = "deny"

            if error is None and sandbox_policy == "deny":
                error = f"Blocked by sandbox policy: {tool} is denied."
            elif error is None and sandbox_policy == "ask":
                callback = getattr(sandbox, "ask_callback", None)
                if callback is None:
                    error = f"Blocked by sandbox policy: {tool} requires approval."
                else:
                    try:
                        approval = callback(tool, args)
                        if hasattr(approval, "__await__"):
                            approval = await approval
                        if not approval:
                            error = f"Blocked by sandbox policy: {tool} was not approved."
                    except Exception:
                        error = f"Blocked by sandbox policy: {tool} approval failed."

            if error is None:
                try:
                    approved = await permissions.decide(tool, args, tool_permission)
                except Exception:
                    approved = False
                if not approved:
                    error = f"Permission denied: {tool} requires approval."

        if error is not None:
            entry = {"tool": tool, "ok": False, "error": error}
        else:
            try:
                result = await registry.execute(tool, args, approved=True)
            except Exception as exc:
                result = ToolResult(name=tool, ok=False,
                                    error=f"{type(exc).__name__}: {exc}")
            entry = {"tool": tool, "ok": result.ok,
                     "output": (result.content or "")[:2000],
                     "error": result.error}
        ok_all = ok_all and bool(entry["ok"])
        results.append(entry)
        if trajectory is not None:
            try:
                trajectory.append("tool.call", f"{tool} (ptc)", data=entry)
            except Exception:
                pass
    return {"ok": ok_all, "steps": len(results), "results": results}
