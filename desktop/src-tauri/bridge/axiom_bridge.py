"""AXIOM desktop bridge: JSONL stdio between the Tauri shell (Rust) and the
real Python core (ChatSession — Ollama, streaming, tools, history).

  request: {"req": 1, "cmd": "send", "args": {...}}
  reply:   {"type": "reply", "req": 1, "ok": true, "data": ...}
  event:   {"type": "event", "event": {type: "reasoning"|"content"|...}}
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading

from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.events import ChatEvent

OUT_LOCK = threading.Lock()


def _model_json(m, loaded: bool = False) -> dict:
    return {
        "name": m.name,
        "displayName": m.display_name,
        "sizeGb": m.size_gb,
        "sizeBytes": m.size,
        "parameterSize": m.parameter_size,
        "quantization": m.quantization,
        "family": m.family,
        "capabilities": m.capabilities,
        "contextLength": m.context_length,
        "numCtx": m.num_ctx,
        "loaded": loaded,
    }


async def _models_json(session: ChatSession) -> list[dict]:
    """Models plus their real in-memory state from ``/api/ps``."""
    models = await session.refresh_models()
    loaded = await session.registry.running_names()
    return [_model_json(m, loaded=m.name in loaded) for m in models]


def _conversation_summary(c) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "model": c.model,
        "createdAt": c.created_at,
        "updatedAt": c.updated_at,
        "messageCount": len(c.messages),
    }


def _conversation_full(c) -> dict:
    data = _conversation_summary(c)
    data["messages"] = [
        {
            "role": m.role,
            "content": m.content,
            "thinking": m.thinking,
            "name": m.name,
            "images": list(m.images or []),
        }
        for m in c.messages
    ]
    return data


def _event_json(e: ChatEvent) -> dict:
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

    if isinstance(e, (ReasoningChunk, ContentChunk)):
        return {"type": e.type, "text": e.text}
    if isinstance(e, ToolCallEvent):
        return {"type": e.type, "name": e.name, "arguments": e.arguments}
    if isinstance(e, ToolResultEvent):
        return {
            "type": e.type,
            "name": e.name,
            "ok": e.ok,
            "content": e.content,
            "error": e.error,
            "durationMs": e.duration_ms,
        }
    if isinstance(e, SearchResultEvent):
        return {
            "type": e.type,
            "query": e.query,
            "sources": [
                {"index": s.index, "title": s.title, "url": s.url, "snippet": s.snippet}
                for s in e.sources
            ],
        }
    if isinstance(e, StatusChange):
        return {"type": e.type, "state": e.state.value, "detail": e.detail}
    if isinstance(e, ErrorEvent):
        return {"type": e.type, "message": e.message, "kind": e.kind, "hint": e.hint}
    if isinstance(e, Done):
        return {
            "type": e.type,
            "state": e.state.value,
            "durationMs": e.duration_ms,
            "tokensOut": e.tokens_out,
            "tokensIn": e.tokens_in,
            "tokensPerSecond": e.tokens_per_second,
        }
    return {"type": type(e).__name__}


def _write_line(line: str) -> None:
    with OUT_LOCK:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


async def _state_json(session: ChatSession) -> dict:
    return {
        "state": session.state.value if session.state else "idle",
        "model": session.active_model.name if session.active_model else None,
        "lastMetrics": session.last_metrics or {},
    }


async def _stream_turn(session: ChatSession, events) -> dict:
    """Stream a real generation cycle to the shell, then report the final state."""
    async for event in events:
        line = json.dumps({"type": "event", "event": _event_json(event)}, ensure_ascii=False)
        await asyncio.get_running_loop().run_in_executor(None, _write_line, line)
    return {
        "state": session.state.value,
        "lastMetrics": session.last_metrics or {},
        "conversation": _conversation_summary(session.conversation),
        "activeModel": _model_json(session.active_model) if session.active_model else None,
    }


async def _handle(session: ChatSession, cmd: str, args: dict) -> object:
    if cmd == "health":
        available = await session.client.is_available()
        version = None
        if available:
            try:
                version = await session.client.version()
            except Exception:  # noqa: BLE001 - a version probe must never fail the UI
                version = None
        return {"available": available, "version": version, "url": session.client.base_url}
    if cmd == "status":
        return {
            **_state_json(session),
            "ollamaUrl": session.client.base_url,
            "version": await session.client.version() if await session.client.is_available() else None,
            "activeModel": _model_json(session.active_model) if session.active_model else None,
            "historyCount": len(session.history()),
            "configPath": str(type(session.config).path()),
            "busy": session.busy,
        }
    if cmd == "tools":
        return session.tools_info()
    if cmd == "model_info":
        detail = await session.model_detail(args.get("name"))
        return _model_json(detail) if detail else None
    if cmd == "startup":
        report = await session.startup()
        models = report.models or []
        loaded: set[str] = set()
        if report.ollama_available:
            loaded = await session.registry.running_names()
        return {
            "available": report.ollama_available,
            "version": report.version,
            "error": report.error,
            "hint": report.hint,
            "models": [_model_json(m, loaded=m.name in loaded) for m in models],
            "selected": _model_json(report.selected) if report.selected else None,
            "state": await _state_json(session),
        }
    if cmd == "reconnect":
        report = await session.reconnect(args.get("url"))
        loaded = await session.registry.running_names() if report.ollama_available else set()
        return {
            "available": report.ollama_available,
            "version": report.version,
            "error": report.error,
            "hint": report.hint,
            "models": [_model_json(m, loaded=m.name in loaded) for m in (report.models or [])],
            "selected": _model_json(report.selected) if report.selected else None,
            "state": await _state_json(session),
        }
    if cmd == "models":
        return await _models_json(session)
    if cmd == "send":
        return await _stream_turn(
            session,
            session.send(
                args.get("text", ""),
                force_search=bool(args.get("forceSearch", False)),
                search_query=args.get("searchQuery"),
                images=[str(img) for img in (args.get("images") or []) if img],
            ),
        )
    if cmd == "regenerate":
        return await _stream_turn(
            session,
            session.regenerate(force_search=bool(args.get("forceSearch", False))),
        )
    if cmd == "edit_message":
        return await _stream_turn(
            session,
            session.edit_last_user(
                args.get("text", ""),
                force_search=bool(args.get("forceSearch", False)),
            ),
        )
    if cmd == "cancel":
        return {"cancelled": session.cancel()}
    if cmd == "new_chat":
        return _conversation_full(session.new_conversation())
    if cmd == "load_chat":
        conv = session.load_conversation(args["id"])
        return _conversation_full(conv) if conv else None
    if cmd == "delete_chat":
        return {"deleted": session.delete_conversation(args["id"])}
    if cmd == "rename_chat":
        return {"renamed": session.rename_conversation(args["id"], args.get("title", ""))}
    if cmd == "list_chats":
        return [_conversation_summary(c) for c in session.history()]
    if cmd == "get_config":
        return json.loads(session.config.model_dump_json())
    if cmd == "set_config":
        current = session.config.model_dump()
        for key, value in (args.get("patch") or {}).items():
            if key in current:
                current[key] = value
        new_cfg = Config.model_validate(current)
        new_cfg.save()
        session.config = new_cfg
        # Agent and web tool read live attributes; update them defensively.
        agent = getattr(session, "agent", None)
        if agent is not None:
            setattr(agent, "config", new_cfg)
        web_tool = getattr(session, "web_tool", None)
        if web_tool is not None:
            setattr(web_tool, "max_sources", new_cfg.search_max_sources)
        provider = getattr(session, "provider", None)
        if provider is not None and provider.__class__.__name__ == "MultiSearchProvider":
            from axiom.core.search.multi import MultiSearchProvider

            session.provider = MultiSearchProvider(provider.providers, timeout=new_cfg.search_timeout)
            if agent is not None:
                agent._web_tool._provider = session.provider
        history_store = getattr(session, "history_store", None)
        if history_store is not None:
            history_store.set_limit(new_cfg.history_limit if new_cfg.save_history else None)
        return json.loads(new_cfg.model_dump_json())
    if cmd == "set_model":
        return _model_json(await session.switch_model(args["name"]))
    if cmd == "state":
        return await _state_json(session)
    raise ValueError(f"Unknown command: {cmd}")


async def _run() -> None:
    loop = asyncio.get_running_loop()
    session = ChatSession()

    async def dispatch(req_id: int, coro) -> None:
        try:
            data = await coro
            reply = json.dumps(
                {"type": "reply", "req": req_id, "ok": True, "data": data},
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001 - bridge must never die on one bad request
            reply = json.dumps(
                {"type": "reply", "req": req_id, "ok": False, "error": str(exc)},
                ensure_ascii=False,
            )
        await loop.run_in_executor(None, _write_line, reply)

    def on_line(raw: str) -> None:
        try:
            request = json.loads(raw)
            req_id = int(request.get("req", 0))
            cmd = str(request.get("cmd", ""))
            args = request.get("args") or {}
            asyncio.run_coroutine_threadsafe(dispatch(req_id, _handle(session, cmd, args)), loop)
        except Exception as exc:  # noqa: BLE001
            _write_line(json.dumps({"type": "reply", "req": 0, "ok": False, "error": str(exc)}))

    def pump() -> None:
        for raw in sys.stdin:
            raw = raw.strip()
            if raw:
                on_line(raw)
        # stdin closed — the shell is gone (killed, crashed or restarted).
        # Exit immediately so no orphaned bridge keeps running and, worse,
        # keeps answering stale requests against a dead UI.
        os._exit(0)

    threading.Thread(target=pump, daemon=True).start()
    await asyncio.Event().wait()  # run until the shell closes stdin


def main() -> None:
    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    main()

