"""AXIOM CLI frontend — a thin adapter over the CORE.

Deliberately free of any TUI dependency: this frontend exists to prove that the
core is truly frontend-agnostic and to make AXIOM scriptable.

    axiom                     → TUI (see axiomn.__main__ dispatch)
    axiom -p "hello"          → one-shot answer on stdout
    axiom --json -p "hello"   → NDJSON event stream (machine readable)
    echo "hello" | axiom      → pipe mode
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from axiom import __version__
from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.events import (
    ContentChunk,
    Done,
    ErrorEvent,
    ReasoningChunk,
    SearchResultEvent,
    StatusChange,
    ToolCallEvent,
    ToolResultEvent,
)
from axiom.shared import formatting as fmt
from axiom.shared import theme

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axiom",
        description="AXIOM — Local Intelligence Terminal Workspace (CLI frontend).",
        epilog='Examples:  axiom -p "explain asyncio"   |   echo "hi" | axiom --json',
    )
    parser.add_argument("prompt", nargs="?", help="Prompt to send (or use -p).")
    parser.add_argument("-p", "--prompt", dest="prompt_flag", help="Prompt to send.")
    parser.add_argument("-m", "--model", help="Model name to use for this run.")
    parser.add_argument("-s", "--search", action="store_true", help="Force a web search before answering.")
    parser.add_argument("--no-search", action="store_true", help="Disable web search for this run.")
    parser.add_argument("--think", choices=["auto", "on", "off"], default=None, help="Reasoning mode.")
    parser.add_argument("--show-reasoning", action="store_true", help="Print real reasoning to stderr.")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Emit an NDJSON event stream.")
    parser.add_argument("--list-models", action="store_true", help="List models available in Ollama and exit.")
    parser.add_argument("--ollama-url", help="Override the Ollama URL for this run.")
    parser.add_argument("--version", action="version", version=f"AXIOM {__version__}")
    return parser


def _read_prompt(args: argparse.Namespace) -> str | None:
    """Prompt from arguments, else from stdin when piped."""
    if args.prompt_flag:
        return args.prompt_flag
    if args.prompt:
        return args.prompt
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        return data if data.strip() else None
    return None


def _build_config(args: argparse.Namespace) -> Config:
    config = Config.load()
    if args.ollama_url:
        config.ollama_url = args.ollama_url
    if args.model:
        config.model = args.model
    if args.no_search:
        config.web_search_enabled = False
    elif args.search:
        # -s explicitly demands a search for this run: it must work even when
        # the stored setting disables it.
        config.web_search_enabled = True
    if args.think == "on":
        config.think = True
    elif args.think == "off":
        config.think = False
    elif args.think == "auto":
        config.think = None
    return config


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _style(text: str, color: str | None = None, *, dim: bool = False, bold: bool = False) -> str:
    """Minimal ANSI styling — only when the stream really is a terminal."""
    if not sys.stderr.isatty():
        return text
    prefix = ""
    if bold:
        prefix += "\x1b[1m"
    if dim:
        prefix += "\x1b[2m"
    if color and len(color) == 7 and color.startswith("#"):
        red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
        prefix += f"\x1b[38;2;{red};{green};{blue}m"
    return f"{prefix}{text}\x1b[0m" if prefix else text


def _err(text: str = "") -> None:
    print(text, file=sys.stderr, flush=True)


async def _list_models(config: Config) -> int:
    session = ChatSession(config)
    report = await session.startup()
    if not report.ollama_available or not report.models:
        _err(_style(f"✕ {report.error or 'No models are available.'}", theme.ERROR, bold=True))
        if report.hint:
            _err(_style(f"  {report.hint}", theme.MUTED))
        return EXIT_ERROR
    active = report.selected.name if report.selected else ""
    _err(_style(f"AXIOM · Ollama {report.version} · {session.client.base_url}", theme.MUTED))
    for model in report.models:
        marker = theme.DOT_ACTIVE if model.name == active else theme.DOT_IDLE
        capabilities = ", ".join(model.capabilities) or "capabilities unknown"
        _err(f"{marker} {model.name}  {model.size_gb} GB  {_style(capabilities, theme.MUTED)}")
    return EXIT_OK


async def _consume(session: ChatSession, prompt: str, args: argparse.Namespace) -> int:
    """Render every real event from the core, in text or NDJSON form."""
    exit_code = EXIT_OK
    async for event in session.send(prompt, force_search=args.search):
        if args.as_json:
            print(event.model_dump_json(), flush=True)
            if isinstance(event, Done) and event.state.value == "error":
                exit_code = EXIT_ERROR
            continue

        if isinstance(event, ReasoningChunk):
            if args.show_reasoning:
                _err(_style(event.text, theme.MUTED, dim=True))
        elif isinstance(event, ContentChunk):
            sys.stdout.write(event.text)
            sys.stdout.flush()
        elif isinstance(event, StatusChange):
            _err(_style(fmt.status_line(event.state.value, active=event.state.is_busy), theme.GARNET_ASH))
        elif isinstance(event, ToolCallEvent):
            arguments = json.dumps(event.arguments, ensure_ascii=False)
            _err(_style(f"⇢ {event.name} {arguments}", theme.MUTED))
        elif isinstance(event, ToolResultEvent):
            if event.ok:
                _err(_style(f"✓ {event.name} ({event.duration_ms} ms)", theme.SUCCESS))
            else:
                _err(_style(f"✕ {event.name}: {event.error}", theme.ERROR))
        elif isinstance(event, SearchResultEvent):
            _err(_style(f"\nSources · {event.query}", theme.MUTED))
            _err(fmt.sources_listing(event.sources))
        elif isinstance(event, ErrorEvent):
            _err(_style(f"✕ {event.message}", theme.ERROR, bold=True))
            if event.hint:
                _err(_style(f"  {event.hint}", theme.MUTED))
        elif isinstance(event, Done):
            metrics = []
            duration = fmt.format_duration_ms(event.duration_ms)
            if duration:
                metrics.append(duration)
            if event.tokens_out is not None:
                metrics.append(f"{fmt.format_tokens(event.tokens_out)} tok")
            rate = fmt.format_rate(event.tokens_per_second)
            if rate:
                metrics.append(rate)
            summary = "  ".join(metrics)
            if event.state.value == "completed":
                _err(_style(f"\n✓ Completed  {summary}".rstrip(), theme.SUCCESS))
            elif event.state.value == "cancelled":
                _err(_style(f"\n✕ Cancelled  {summary}".rstrip(), theme.WARNING))
                exit_code = EXIT_INTERRUPTED
            else:
                _err(_style(f"\n✕ Failed  {summary}".rstrip(), theme.ERROR))
                exit_code = EXIT_ERROR
    if not args.as_json:
        sys.stdout.write("\n")
        sys.stdout.flush()
    return exit_code


async def _run(args: argparse.Namespace) -> int:
    config = _build_config(args)
    if args.list_models:
        return await _list_models(config)

    prompt = _read_prompt(args)
    if not prompt:
        _err("Nothing to do: pass a prompt with -p/--prompt, as a positional argument, or via stdin.")
        return EXIT_USAGE

    session = ChatSession(config)
    report = await session.startup()
    selected = report.selected
    if selected is None:
        _err(_style(f"✕ {report.error or 'No model is available.'}", theme.ERROR, bold=True))
        if report.hint:
            _err(_style(f"  {report.hint}", theme.MUTED))
        return EXIT_ERROR
    if not args.as_json:
        _err(
            _style(
                f"AXIOM · {selected.display_name} · Ollama {report.version or 'unknown'}",
                theme.MUTED,
            )
        )
    return await _consume(session, prompt, args)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code (never raises to the user)."""
    _ensure_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        _err(_style("\n✕ Cancelled", theme.WARNING))
        return EXIT_INTERRUPTED
    except Exception as exc:
        _err(_style(f"✕ {type(exc).__name__}: {exc}", theme.ERROR, bold=True))
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
