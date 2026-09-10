"""Streaming helpers: merge tool-call deltas from OpenAI-style chunks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallAccumulator:
    """Accumulates streamed tool_call deltas into complete calls."""

    calls: dict[int, dict[str, Any]] = field(default_factory=dict)

    def add(self, tool_call_delta: dict[str, Any]) -> None:
        index = tool_call_delta.get("index", 0)
        entry = self.calls.setdefault(
            index, {"id": "", "name": "", "arguments": ""}
        )
        if tool_call_delta.get("id"):
            entry["id"] = tool_call_delta["id"]
        fn = tool_call_delta.get("function") or {}
        if fn.get("name"):
            entry["name"] = fn["name"]
        if fn.get("arguments"):
            entry["arguments"] += fn["arguments"]

    def finalize(self) -> list[dict[str, Any]]:
        result = []
        for index in sorted(self.calls):
            entry = self.calls[index]
            try:
                args = json.loads(entry["arguments"]) if entry["arguments"] else {}
            except json.JSONDecodeError:
                args = {"_raw": entry["arguments"]}
            result.append(
                {"id": entry["id"] or f"call_{index}", "name": entry["name"], "arguments": args}
            )
        return result
