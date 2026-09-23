"""Context Engine — что отправить модели (п.9).

Собирает: user request + relevant files + symbols + git diff +
previous trajectory + skills + tool results + project rules.
Компрессия — через summarizer-колбэк; Trajectory остаётся целой.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from axiom.core.context import ContextManager

Summarizer = Callable[[str], Awaitable[str | None]]


@dataclass
class BuiltContext:
    messages: list[dict] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    git_diff: str = ""
    trajectory_summary: str = ""
    compressed: bool = False
    report: dict = field(default_factory=dict)


class ContextEngine:
    def __init__(self, max_tokens: int | None = None) -> None:
        self._manager = ContextManager(max_tokens=max_tokens)

    def estimate(self, text: str) -> int:
        return int(len(text or "") / 4)

    def _read_files(self, root: Path | None, paths: list[str], budget_chars: int = 24000) -> list[str]:
        chunks: list[str] = []
        if root is None:
            return chunks
        used = 0
        for rel in paths[:12]:
            try:
                target = (root / rel).resolve()
                if root.resolve() not in target.parents and target != root.resolve():
                    continue
                text = target.read_text(encoding="utf-8", errors="replace")
                block = f"### {rel}\n{text[:6000]}"
                if used + len(block) > budget_chars:
                    break
                chunks.append(block)
                used += len(block)
            except Exception:
                continue
        return chunks

    def _git_diff(self, root: Path | None, limit: int = 8000) -> str:
        if root is None:
            return ""
        try:
            import subprocess
            proc = subprocess.run(["git", "diff", "--no-color"], cwd=root,
                                  stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=10, check=False)
            out = proc.stdout or ""
            return out[:limit]
        except Exception:
            return ""

    def build(self, user_text: str, history: list[dict], *,
              system_prompt: str = "", workspace_root: Path | str | None = None,
              file_paths: list[str] | None = None, skills: list[str] | None = None,
              tool_results: list[str] | None = None,
              trajectory_tail: list[dict] | None = None) -> BuiltContext:
        root = Path(workspace_root) if workspace_root else None
        files = self._read_files(root, file_paths or [], budget_chars=24000)
        git_diff = self._git_diff(root)
        blocks: list[str] = []
        if skills:
            blocks.append("Skills:\n" + "\n".join(f"- {s}" for s in skills[:12]))
        if trajectory_tail:
            tail = trajectory_tail[-8:]
            blocks.append("Previous trajectory:\n" + "\n".join(
                f"- [{t.get('kind')}] {t.get('summary')}" for t in tail))
        if tool_results:
            blocks.append("Tool results:\n" + "\n".join(tool_results[-6:])[:6000])
        if files:
            blocks.append("Relevant files:\n" + "\n\n".join(files))
        if git_diff.strip():
            blocks.append("Git diff:\n" + git_diff)
        context_block = "\n\n".join(blocks)
        system = system_prompt or ""
        if context_block:
            system = f"{system}\n\n{context_block}".strip()
        messages = self._manager.prepare(list(history or []), system or None)
        report = {"estimated_tokens": self._manager.report.estimated_tokens,
                  "kept": self._manager.report.kept_count, "files": len(files),
                  "git_diff_chars": len(git_diff)}
        return BuiltContext(messages=messages, files=[f.splitlines()[0] for f in files],
                            git_diff=git_diff, report=report)

    async def compress(self, messages: list[dict], summarizer: Summarizer | None = None,
                       preserve_count: int = 6) -> tuple[list[dict], bool]:
        if summarizer is None or not messages:
            return messages, False
        lines = []
        for msg in messages[:-preserve_count] if len(messages) > preserve_count else []:
            content = str(msg.get("content") or "")
            if content:
                lines.append(f"{msg.get('role')}: {content[:500]}")
        if not lines:
            return messages, False
        try:
            summary = await summarizer("\n".join(lines[-20:]))
        except Exception:
            return messages, False
        if not summary or not summary.strip():
            return messages, False
        compacted = self._manager.compact(messages, summary.strip(), preserve_count=preserve_count)
        return compacted, True
