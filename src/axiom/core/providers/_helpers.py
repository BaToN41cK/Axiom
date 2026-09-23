"""Хелперы OpenAI-совместимого адаптера."""
from __future__ import annotations

import json as _json

from axiom.core.providers.base import ToolCall


def headers(api_key: str, extra: dict | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    if extra:
        h.update(extra)
    return h

def to_messages(messages) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]

def parse_tool_calls(raw: list[dict]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in raw or []:
        fn = item.get("function", {}) if isinstance(item, dict) else {}
        name = fn.get("name") if isinstance(fn, dict) else None
        if not name:
            continue
        args = fn.get("arguments", {}) if isinstance(fn, dict) else {}
        if isinstance(args, str):
            try:
                args = _json.loads(args) if args.strip() else {}
            except Exception:
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {}
        calls.append(ToolCall(name=str(name), arguments=args))
    return calls
