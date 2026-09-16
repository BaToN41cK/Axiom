"""AXIOM GUI frontend — a Tkinter adapter over the core event stream.

The same rules as the TUI and the CLI apply: every status, reasoning delta
and search source is a projection of a real ``ChatEvent`` from
``ChatSession.send()`` — nothing here is simulated. Tkinter is used so the
GUI ships with zero additional dependencies (UI ≠ LOGIC: this module talks
to the core only through ``ChatSession`` and ``ChatEvent``).
"""

from __future__ import annotations

import asyncio
import threading
import time
import tkinter as tk
import webbrowser
from queue import Empty, Queue
from tkinter import ttk

from axiom.core.chat import ChatSession
from axiom.core.errors import AxiomError
from axiom.core.events import (
    ContentChunk,
    Done,
    ErrorEvent,
    ReasoningChunk,
    SearchResultEvent,
    SourceItem,
    StatusChange,
    ToolResultEvent,
)
from axiom.core.models import ModelRegistry
from axiom.core.tools.web_search import FETCH_URL_TOOL, WEB_SEARCH_TOOL
from axiom.shared import formatting as fmt
from axiom.shared import logo as logo_art
from axiom.shared import theme as palette

POLL_MS = 40
SPIN_MS = int(palette.SPINNER_INTERVAL * 1000)
FONT = ("Consolas", 10)
FONT_BOLD = ("Consolas", 10, "bold")
FONT_SMALL = ("Consolas", 9)


def _text(parent, *, bg: str, fg: str) -> tk.Text:
    """A borderless, word-wrapping, read-only text widget."""
    return tk.Text(
        parent, wrap="word", borderwidth=0, highlightthickness=0, relief="flat",
        takefocus=0, padx=0, pady=0, font=FONT, bg=bg, fg=fg, height=1,
        state="disabled",
    )


def _autosize(widget: tk.Text, cap: int = 10_000) -> None:
    """Grow a Text widget to its content (display lines, wraps included)."""
    lines = int(widget.index("end-1c").split(".", 1)[0])
    widget.configure(height=max(1, min(lines, cap)))


def _label(parent, text="", *, bg=palette.BLACK, fg=palette.MUTED, font=FONT_SMALL):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=font, anchor="w", justify="left")


def _insert(widget: tk.Text, text: str) -> None:
    widget.configure(state="normal")
    widget.insert("end", text)
    widget.configure(state="disabled")
    _autosize(widget)


class SearchBlock(tk.Frame):
    """Web-search progress and clickable sources (mirrors the TUI panel)."""

    def __init__(self, parent, on_open) -> None:
        super().__init__(parent, bg=palette.BLACK)
        self._on_open = on_open
        self._tick = 0
        self._query = ""
        self._searching = False
        self._sources: list[SourceItem] = []
        self._reading: dict[str, str] = {}
        self._read_done = 0
        self._read_failed = 0
        self._error: str | None = None
        self.steps = _label(self, fg=palette.MUTED)
        self.steps.pack(fill="x", padx=(24, 0), pady=(2, 0))
        self.source_frame = tk.Frame(self, bg=palette.BLACK)
        self.source_frame.pack(fill="x", padx=(32, 0), pady=(0, 4))

    # ------------------------------------------------------------------ events

    def search_started(self, query: str) -> None:
        self._query = query
        self._searching = True
        self._refresh()

    def search_finished(self, query: str, sources: list[SourceItem]) -> None:
        self._query = query or self._query
        self._searching = False
        self._sources = list(sources)
        for child in list(self.source_frame.children.values()):
            child.destroy()
        for source in self._sources:
            row = tk.Label(
                self.source_frame,
                text=f"{source.index:02d}  {fmt.truncate(source.title or source.url, 88)}",
                bg=palette.BLACK, fg=palette.SILVER, font=FONT_SMALL, anchor="w",
                cursor="hand2",
            )
            row.pack(fill="x")
            url = source.url
            row.bind("<Button-1>", lambda _e, url=url: self._on_open(url))
            row.bind("<Enter>", lambda _e, w=row: w.configure(fg=palette.WHITE))
            row.bind("<Leave>", lambda _e, w=row: w.configure(fg=palette.SILVER))
        self._refresh()

    def search_failed(self, message: str) -> None:
        self._searching = False
        self._error = message
        self._refresh()

    def read_started(self, url: str) -> None:
        self._reading[url] = "active"
        self._refresh()

    def read_finished(self, url: str, ok: bool) -> None:
        self._reading[url] = "ok" if ok else "failed"
        if ok:
            self._read_done += 1
        else:
            self._read_failed += 1
        self._refresh()

    def set_tick(self, tick: int) -> None:
        self._tick = tick
        if self._searching or any(v == "active" for v in self._reading.values()):
            self._refresh()

    def finish(self) -> None:
        self._searching = False
        self._refresh()

    # ----------------------------------------------------------------- private

    def _refresh(self) -> None:
        lines: list[str] = []
        if self._error and not self._sources:
            lines.append(f"{palette.CROSS} Search  {self._error}")
        elif self._searching:
            lines.append(f"{fmt.spinner_frame(self._tick)} Searching  {fmt.truncate(self._query, 70)}")
        elif self._sources:
            lines.append(
                f"{palette.TICK} Search  {fmt.truncate(self._query, 60)}  ·  {len(self._sources)} sources"
            )
        elif self._query:
            lines.append(f"{palette.CROSS} Search  {fmt.truncate(self._query, 70)}  ·  no results")

        active_reads = sum(1 for v in self._reading.values() if v == "active")
        total_reads = self._read_done + self._read_failed + active_reads
        if total_reads:
            if active_reads:
                lines.append(
                    f"{fmt.spinner_frame(self._tick)} Reading sources  ·  {self._read_done}/{total_reads}"
                )
            else:
                failed = f"  ·  {self._read_failed} failed" if self._read_failed else ""
                lines.append(f"{palette.TICK} Reading sources  ·  {self._read_done}/{total_reads}{failed}")
        self.steps.configure(text="\n".join(lines))

class AssistantBlock(tk.Frame):
    """One assistant turn: status, thinking, search, answer, metrics, error."""

    def __init__(self, parent, on_open_source, *, animations=True, reasoning_expanded=False):
        super().__init__(parent, bg=palette.BLACK)
        self._on_open_source = on_open_source
        self._animations = animations
        self._tick = 0
        self._state = "connecting"
        self._busy = True
        self._detail: str | None = None
        self._duration_ms: int | None = None
        self._open = reasoning_expanded
        self._has_thinking = False
        self.finished = False
        self.answering = False

        self.status = _label(self, fg=palette.MUTED)
        self.status.pack(fill="x", padx=(16, 0))

        self.thinking_area = tk.Frame(self, bg=palette.BLACK)
        self.thinking_area.pack(fill="x")

        self.toggle = tk.Label(
            self.thinking_area, text="", bg=palette.BLACK, fg=palette.SILVER,
            font=FONT_SMALL, anchor="w", cursor="hand2",
        )
        self.toggle.bind("<Button-1>", lambda _e: self.toggle_thinking())

        self.thinking = _text(self.thinking_area, bg=palette.VOID, fg=palette.MUTED)

        self.search_area = tk.Frame(self, bg=palette.BLACK)
        self.search_area.pack(fill="x")

        self.search = SearchBlock(self.search_area, on_open_source)

        self.answer_area = tk.Frame(self, bg=palette.BLACK)
        self.answer_area.pack(fill="x")

        self.answer_label = _label(self.answer_area, text="ANSWER", fg=palette.BRONZE, font=FONT_BOLD)
        self.answer = _text(self.answer_area, bg=palette.BLACK, fg=palette.WHITE)

        self.bottom_area = tk.Frame(self, bg=palette.BLACK)
        self.bottom_area.pack(fill="x")

        self.metrics = _label(self.bottom_area, fg=palette.MUTED)
        self.error = _label(self.bottom_area, fg=palette.ERROR)
        self.refresh_status()

    # ------------------------------------------------------------------- status

    def set_tick(self, tick: int) -> None:
        self._tick = tick
        self.search.set_tick(tick)
        self.refresh_status()
        self._refresh_toggle()

    def set_state(self, state_value: str, *, busy: bool, detail: str | None = None) -> None:
        self._state = state_value
        self._busy = busy
        if detail is not None:
            self._detail = detail
        self.refresh_status()
        self._refresh_toggle()

    def refresh_status(self) -> None:
        if self.finished and self._state == "completed" and self.answering:
            self.status.configure(text="")
            return
        if self._state == "thinking" and self._has_thinking:
            # The THINKING toggle already carries this phase; a second status
            # line would show the user two "Thinking" rows.
            self.status.configure(text="")
            return
        self.status.configure(
            text=fmt.status_line(
                self._state,
                tick=self._tick,
                duration_ms=self._duration_ms,
                detail=self._detail,
                active=self._busy,
            )
        )

    # ----------------------------------------------------------------- thinking

    def append_thinking(self, text: str) -> None:
        if not self._has_thinking:
            self._has_thinking = True
            self.toggle.configure(text=self._toggle_title())
            self.toggle.pack(fill="x", padx=(16, 0))
            if self._open:
                self.thinking.pack(fill="x", padx=(24, 0), pady=(2, 4), after=self.toggle)
        _insert(self.thinking, text)

    def toggle_thinking(self) -> None:
        if not self._has_thinking:
            return
        self._open = not self._open
        if self._open:
            self.thinking.pack(fill="x", padx=(24, 0), pady=(2, 4), after=self.toggle)
        else:
            self.thinking.pack_forget()
        self._refresh_toggle()

    def thinking_content(self) -> str:
        return self.thinking.get("1.0", "end-1c")

    def _toggle_title(self) -> str:
        arrow = "▾" if self._open else "▸"
        return (
            f"{arrow} "
            + fmt.status_line(
                self._state,
                tick=self._tick,
                duration_ms=self._duration_ms,
                detail=self._detail,
                active=self._busy,
            )
        )

    def _refresh_toggle(self) -> None:
        if self._has_thinking:
            self.toggle.configure(text=self._toggle_title())

    # ------------------------------------------------------------------- search

    def reveal_search(self) -> None:
        self.search.pack(fill="x")

    # ------------------------------------------------------------------- answer

    def begin_answer(self) -> None:
        if self.answering:
            return
        self.answering = True
        self.answer_label.pack(fill="x", padx=(16, 0), pady=(2, 0))
        self.answer.pack(fill="x", padx=(24, 0), pady=(2, 4), after=self.answer_label)

    def append_answer(self, text: str) -> None:
        _insert(self.answer, text)

    def answer_text(self) -> str:
        return self.answer.get("1.0", "end-1c")

    # ---------------------------------------------------------- finish / errors

    def finish(
        self,
        state_value: str,
        duration_ms: int | None,
        tokens_out: int | None = None,
        tokens_per_second: float | None = None,
    ) -> None:
        self.finished = True
        self._busy = False
        self._state = state_value
        self._duration_ms = duration_ms
        self.search.finish()
        # Fold the live reasoning away: thinking is a temporary live-view,
        # the toggle summary (▸ Thinking · duration) stays.
        if self._has_thinking and self._open:
            self._open = False
            self.thinking.pack_forget()
        self.refresh_status()
        self._refresh_toggle()
        parts: list[str] = []
        duration = fmt.format_duration_ms(duration_ms)
        if duration:
            parts.append(duration)
        if tokens_out is not None:
            parts.append(f"{fmt.format_tokens(tokens_out)} tok")
        rate = fmt.format_rate(tokens_per_second)
        if rate:
            parts.append(rate)
        if parts:
            self.metrics.configure(text="  ".join(parts))
            try:
                self.metrics.pack(fill="x", padx=(24, 0), pady=(0, 8), before=self.error)
            except tk.TclError:  # error box not shown — metrics go to the end
                self.metrics.pack(fill="x", padx=(24, 0), pady=(0, 8))

    def add_error(self, message: str, hint: str | None = None) -> None:
        text = f"{palette.CROSS} {message}"
        if hint:
            text += f"\n   {hint}"
        self.error.configure(text=text)
        self.error.pack(fill="x", padx=(16, 0), pady=(4, 8))


class UserBlock(tk.Frame):
    """A user turn (never re-rendered once added)."""

    def __init__(self, parent, text: str, timestamp: float | None = None) -> None:
        super().__init__(parent, bg=palette.BLACK)
        stamp = fmt.format_clock(timestamp)
        label = "YOU" + (f"  ·  {stamp}" if stamp else "")
        _label(self, text=label, fg=palette.MUTED).pack(fill="x", padx=(16, 0))
        body = _text(self, bg=palette.BLACK, fg=palette.WHITE)
        body.pack(fill="x", padx=(24, 0), pady=(2, 0))
        _insert(body, text)

class AxiomTk:
    """The AXIOM GUI application: Tkinter UI + a background asyncio loop.

    The Tk main thread owns all widgets; the core runs on a daemon thread and
    communicates through a queue, so the UI never blocks on I/O.
    """

    def __init__(self, session: ChatSession) -> None:
        self.session = session
        self.events: Queue = Queue()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop_main, daemon=True)
        self._busy = False
        self._version: str | None = None
        self._workspace_ready = False
        self._follow = True
        self._tick = 0
        self._assistant: AssistantBlock | None = None
        self._read_queue: list[SourceItem] = []
        self._read_index = 0
        self._sb_state = "idle"
        self._sb_detail: str | None = None
        self._sb_busy = False
        self._tokens: int | None = None
        self._rate: float | None = None
        self._display_by_name: dict[str, str] = {}
        self._step_labels: dict[str, tk.Label] = {}

        self.root = tk.Tk()
        self.root.title("AXIOM")
        self.root.configure(bg=palette.BLACK)
        self.root.geometry("960x720")
        self.root.minsize(640, 420)
        self._style()
        self._thread.start()
        self._build_splash()
        self.root.after(POLL_MS, self._poll)
        self.root.after(SPIN_MS, self._spin)
        self.root.bind("<End>", lambda _e: self._jump_to_end())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------------- plumbing

    def _loop_main(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _schedule(self, coro) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:  # pragma: no cover - theme always exists in tk 8.6
            pass
        style.configure(
            "TButton", background=palette.GARNET_DEEP, foreground=palette.WHITE,
            bordercolor=palette.GARNET, lightcolor=palette.GARNET_DEEP,
            darkcolor=palette.GARNET_DEEP, focusthickness=0,
        )
        style.map(
            "TButton",
            background=[("active", palette.GARNET), ("disabled", palette.ASH_DEEP)],
            foreground=[("disabled", palette.MUTED)],
        )
        style.configure(
            "TCombobox", fieldbackground=palette.ASH_DEEP, background=palette.ASH_DEEP,
            foreground=palette.WHITE, arrowcolor=palette.SILVER,
            bordercolor=palette.GARNET, lightcolor=palette.ASH_DEEP,
            darkcolor=palette.ASH_DEEP,
        )
        style.configure(
            "Vertical.TScrollbar", background=palette.ASH_DEEP, troughcolor=palette.BLACK,
            bordercolor=palette.BLACK, arrowcolor=palette.MUTED,
        )

    # ------------------------------------------------------------------- splash

    def _build_splash(self) -> None:
        self.splash = tk.Frame(self.root, bg=palette.BLACK)
        self.splash.pack(expand=True, fill="both")
        tk.Label(
            self.splash, text="\n".join(logo_art.LOGO_ART), bg=palette.BLACK,
            fg=palette.WHITE, font=FONT_BOLD, justify="center",
        ).pack(pady=(48, 8))
        tk.Label(
            self.splash, text=logo_art.SUBTITLE, bg=palette.BLACK,
            fg=palette.MUTED, font=FONT_SMALL,
        ).pack()
        self.steps_frame = tk.Frame(self.splash, bg=palette.BLACK)
        self.steps_frame.pack(fill="x", padx=24, pady=(24, 0))
        self.splash_message = _label(self.splash, text="", fg=palette.MUTED)
        self.splash_message.pack(fill="x", padx=24, pady=(12, 0))
        self.actions = tk.Frame(self.splash, bg=palette.BLACK)
        self.actions.pack(pady=(12, 0))
        self._schedule(self._startup_coro())

    def _on_step_start(self, title: str) -> None:
        label = _label(self.steps_frame, text=f"◌  {title}", fg=palette.MUTED)
        label.pack(fill="x")
        self._step_labels[title] = label

    def _on_step_done(self, title: str, ok: bool, note: str) -> None:
        label = self._step_labels.get(title)
        if label is None:
            return
        glyph = palette.TICK if ok else palette.CROSS
        label.configure(
            text=f"{glyph}  {title}{('   ' + note) if note else ''}",
            fg=palette.SUCCESS if ok else palette.ERROR,
        )

    def _on_startup_fail(self, reason: str, hint: str) -> None:
        text = f"{palette.CROSS} {reason}"
        if hint:
            text += f"\n{hint}"
        self.splash_message.configure(text=text, fg=palette.ERROR)
        retry = tk.Label(
            self.actions, text=" Retry ", bg=palette.BLACK, fg=palette.SILVER,
            font=FONT, cursor="hand2", relief="solid", borderwidth=1,
        )
        exit_label = tk.Label(
            self.actions, text=" Exit ", bg=palette.BLACK, fg=palette.SILVER,
            font=FONT, cursor="hand2", relief="solid", borderwidth=1,
        )
        retry.pack(side="left", padx=6)
        exit_label.pack(side="left", padx=6)
        retry.bind("<Button-1>", lambda _e: self._retry_startup())
        exit_label.bind("<Button-1>", lambda _e: self.root.destroy())

    def _retry_startup(self) -> None:
        for child in list(self.steps_frame.children.values()):
            child.destroy()
        self._step_labels = {}
        self.splash_message.configure(text="", fg=palette.MUTED)
        for child in list(self.actions.children.values()):
            child.destroy()
        self._schedule(self._startup_coro())

    def _on_startup_ok(self) -> None:
        self._workspace_ready = True
        self.splash.destroy()
        self._build_workspace()

    # ----------------------------------------------------------- startup probes

    async def _startup_coro(self) -> None:
        q = self.events
        try:
            q.put(("step_start", "Connecting to Ollama"))
            if not await self.session.client.is_available():
                q.put((
                    "startup_fail",
                    f"Ollama is not reachable at {self.session.client.base_url}",
                    "Start Ollama and make sure it is listening.",
                ))
                return
            version = await self.session.client.version()
            self._version = version
            q.put(("step_done", "Connecting to Ollama", True, f"Ollama {version}"))

            q.put(("step_start", "Detecting models"))
            models = await self.session.registry.refresh()
            if not models:
                q.put((
                    "startup_fail",
                    "No models are installed.",
                    "Install one with: ollama pull qwen3:8b",
                ))
                return
            q.put(("step_done", "Detecting models", True, f"{len(models)} model(s)"))

            q.put(("step_start", "Selecting model"))
            model = self.session.registry.resolve(self.session.config.model)
            if model is None:
                q.put(("startup_fail", "No model is available.", ""))
                return
            self.session.active_model = model
            self.session.conversation.model = model.name
            ModelRegistry.persist_selection(self.session.config, model.name)
            q.put(("step_done", "Selecting model", True, model.display_name))

            q.put(("step_start", "Initializing workspace"))
            self.session.config.save()
            q.put(("step_done", "Initializing workspace", True, ""))
            q.put(("startup_ok",))
        except AxiomError as exc:
            q.put(("startup_fail", str(exc), exc.hint or ""))
        except Exception as exc:
            q.put(("startup_fail", f"{type(exc).__name__}: {exc}", ""))

    # ---------------------------------------------------------------- workspace

    def _build_workspace(self) -> None:
        header = tk.Frame(self.root, bg=palette.OBSIDIAN, height=34)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text=" AXIOM", bg=palette.OBSIDIAN, fg=palette.WHITE, font=FONT_BOLD,
        ).pack(side="left", padx=(10, 14))
        self.model_box = ttk.Combobox(header, state="readonly", width=26, font=FONT_SMALL)
        self.model_box.pack(side="left")
        self.model_box.bind("<<ComboboxSelected>>", self._on_model_selected)
        buttons = tk.Frame(header, bg=palette.OBSIDIAN)
        buttons.pack(side="right", padx=8)
        for text, command in (
            ("New", self._new_chat),
            ("Models", self._show_models),
            ("Settings", self._show_settings),
            ("History", self._show_history),
        ):
            button = tk.Label(
                buttons, text=text, bg=palette.OBSIDIAN, fg=palette.SILVER,
                font=FONT_SMALL, cursor="hand2", padx=8,
            )
            button.pack(side="left")
            button.bind("<Button-1>", lambda _e, c=command: c())

        chat_holder = tk.Frame(self.root, bg=palette.BLACK)
        chat_holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(chat_holder, bg=palette.BLACK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(chat_holder, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.chat_inner = tk.Frame(self.canvas, bg=palette.BLACK)
        self._chat_window = self.canvas.create_window((0, 0), window=self.chat_inner, anchor="nw")
        self.chat_inner.bind(
            "<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self._chat_window, width=e.width)
        )
        self.root.bind_all("<MouseWheel>", self._on_wheel)

        input_area = tk.Frame(self.root, bg=palette.OBSIDIAN)
        input_area.pack(fill="x")
        self.input = tk.Text(
            input_area, height=3, wrap="word", bg=palette.VOID, fg=palette.WHITE,
            insertbackground=palette.WHITE, font=FONT, relief="flat", padx=8, pady=6,
            borderwidth=0, highlightthickness=1,
            highlightbackground=palette.GARNET_DEEP, highlightcolor=palette.GARNET,
        )
        self.input.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)
        self.input.bind("<Return>", self._on_return)
        self.input.focus_set()
        action_buttons = tk.Frame(input_area, bg=palette.OBSIDIAN)
        action_buttons.pack(side="right", padx=(0, 8), pady=8)
        self.stop_btn = ttk.Button(action_buttons, text="Stop", command=self._on_stop, state="disabled", width=8)
        self.stop_btn.pack(side="top", pady=(0, 6))
        self.send_btn = ttk.Button(action_buttons, text="Send", command=self._send_from_input, width=8)
        self.send_btn.pack(side="top")

        bar = tk.Frame(self.root, bg=palette.OBSIDIAN, height=24)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status_left = tk.Label(bar, text="", bg=palette.OBSIDIAN, fg=palette.MUTED, font=FONT_SMALL)
        self.status_left.pack(side="left", padx=10)
        self.status_right = tk.Label(bar, text="", bg=palette.OBSIDIAN, fg=palette.MUTED, font=FONT_SMALL)
        self.status_right.pack(side="right", padx=10)
        self._refresh_statusbar()

    def _fill_model_box(self) -> None:
        self._display_by_name = {}
        values: list[str] = []
        for model in self.session.registry.models:
            display = model.display_name
            self._display_by_name[display] = model.name
            values.append(display)
        self.model_box.configure(values=values)
        if self.session.active_model is not None:
            self.model_box.set(self.session.active_model.display_name)

    def _on_model_selected(self, _event=None) -> None:
        name = self._display_by_name.get(self.model_box.get())
        if not name or (self.session.active_model and name == self.session.active_model.name):
            return
        self._schedule(self._switch_model_coro(name))

    async def _switch_model_coro(self, name: str) -> None:
        try:
            model = await self.session.switch_model(name)
            self.events.put(("model_switched", model.display_name))
        except Exception as exc:
            self.events.put(("model_switch_failed", f"{type(exc).__name__}: {exc}"))

    # ------------------------------------------------------------------ scrolling

    def _on_wheel(self, event) -> None:
        amount = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(amount, "units")
        if event.delta > 0:
            self._follow = False

    def _jump_to_end(self) -> None:
        self._follow = True
        self.canvas.yview_moveto(1.0)

    def _scroll_bottom(self) -> None:
        if self._follow:
            self.canvas.yview_moveto(1.0)

    # ------------------------------------------------------------- chat actions

    def _note(self, text: str) -> None:
        label = _label(self.chat_inner, text=text, fg=palette.MUTED)
        label.pack(fill="x", padx=16, pady=(4, 8))
        self._scroll_bottom()

    def _clear_chat(self) -> None:
        for child in list(self.chat_inner.children.values()):
            child.destroy()
        self._assistant = None
        self._follow = True
        self.canvas.yview_moveto(0.0)

    def _new_chat(self) -> None:
        if self._busy:
            return
        self.session.new_conversation()
        self._clear_chat()
        self._note("New conversation.")

    def _add_user_block(self, text: str, timestamp: float | None = None) -> None:
        UserBlock(self.chat_inner, text, timestamp).pack(fill="x", pady=(0, 12))
        self._scroll_bottom()

    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _render_conversation(self, conversation) -> None:
        self._clear_chat()
        for message in conversation.messages:
            if message.role == "user" and message.content:
                self._add_user_block(message.content, message.created_at)
            elif message.role == "assistant" and (message.content or message.thinking):
                assistant = AssistantBlock(
                    self.chat_inner, self._open_url,
                    animations=self.session.config.animations,
                    reasoning_expanded=self.session.config.reasoning_expanded,
                )
                assistant.pack(fill="x", pady=(0, 12))
                if message.thinking:
                    assistant.append_thinking(message.thinking)
                if message.content:
                    assistant.begin_answer()
                    _insert(assistant.answer, message.content)
                assistant.finish("completed", None)
        self._scroll_bottom()

    # ---------------------------------------------------------------- generation

    def _on_return(self, event) -> str | None:
        if event.state & 0x0001:  # Shift held → insert a newline
            return None
        self.root.after(1, self._send_from_input)
        return "break"

    def _send_from_input(self) -> None:
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            return
        if text.startswith("/"):
            self._slash_command(text)
            return
        if self._busy:
            return
        self.input.delete("1.0", "end")
        self._start_generation(text)

    def _slash_command(self, raw: str) -> None:
        token = raw.strip().split()[0].lower()
        argument = raw.strip()[len(token):].strip()
        self.input.delete("1.0", "end")
        if token in ("/new", "/clear"):
            self._new_chat()
        elif token == "/exit":
            self._on_close()
        elif token == "/help":
            self._note("GUI: use the toolbar — New / Models / Settings / History.")
        elif token == "/search" and argument:
            self._start_generation(argument, force_search=True, search_query=argument)
        elif token == "/search":
            self._note("Usage: /search <query>")
        else:
            self._note(f"Unknown command: {token}")

    def _start_generation(
        self, text: str, *, force_search: bool = False, search_query: str | None = None
    ) -> None:
        if self._busy:
            return
        self._add_user_block(text, time.time())
        assistant = AssistantBlock(
            self.chat_inner, self._open_url,
            animations=self.session.config.animations,
            reasoning_expanded=self.session.config.reasoning_expanded,
        )
        assistant.pack(fill="x", pady=(0, 12))
        self._assistant = assistant
        self._busy = True
        self._read_queue = []
        self._read_index = 0
        self._tokens = None
        self._rate = None
        self._sb_state = "connecting"
        self._sb_detail = None
        self._sb_busy = True
        self.stop_btn.configure(state="normal")
        self.send_btn.configure(state="disabled")
        self._refresh_statusbar()
        self._scroll_bottom()
        self._schedule(
            self._send_coro(text, force_search=force_search, search_query=search_query)
        )

    async def _send_coro(
        self, text: str, *, force_search: bool = False, search_query: str | None = None
    ) -> None:
        try:
            async for event in self.session.send(
                text, force_search=force_search, search_query=search_query
            ):
                self.events.put(("event", event))
        except AxiomError as exc:
            self.events.put(("event", ErrorEvent(message=str(exc), kind=exc.kind, hint=exc.hint)))
        except Exception as exc:
            self.events.put((
                "event",
                ErrorEvent(message=f"{type(exc).__name__}: {exc}", kind="internal"),
            ))
        finally:
            self.events.put(("gen_done",))

    def _on_stop(self) -> None:
        if not self._busy:
            return
        self._schedule(self._cancel_coro())

    async def _cancel_coro(self) -> None:
        self.session.cancel()

    # ------------------------------------------------------------ event polling

    def _poll(self) -> None:
        try:
            while True:
                self._handle(self.events.get_nowait())
        except Empty:
            pass
        self.root.after(POLL_MS, self._poll)

    def _handle(self, item) -> None:
        kind = item[0]
        if kind == "step_start":
            self._on_step_start(item[1])
        elif kind == "step_done":
            self._on_step_done(item[1], item[2], item[3])
        elif kind == "startup_ok":
            self._on_startup_ok()
        elif kind == "startup_fail":
            self._on_startup_fail(item[1], item[2])
        elif kind == "event":
            self._dispatch_event(item[1])
        elif kind == "gen_done":
            self._on_generation_done()
        elif kind == "model_switched":
            self.model_box.set(item[1])
            self._refresh_statusbar()
            self._note(f"Model switched to {item[1]}.")
        elif kind == "model_switch_failed":
            self._note(f"{palette.CROSS} {item[1]}")

    def _dispatch_event(self, event) -> None:
        assistant = self._assistant
        if assistant is None:
            return
        if isinstance(event, StatusChange):
            busy = event.state.is_busy
            assistant.set_state(event.state.value, busy=busy, detail=event.detail)
            self._sb_state = event.state.value
            self._sb_detail = event.detail
            self._sb_busy = busy
            self._refresh_statusbar()
            if event.detail == "read_source":
                self._begin_read(assistant)
        elif isinstance(event, ReasoningChunk):
            assistant.append_thinking(event.text)
            self._scroll_bottom()
        elif isinstance(event, ContentChunk):
            assistant.begin_answer()
            _insert(assistant.answer, event.text)
            self._scroll_bottom()
        elif isinstance(event, SearchResultEvent):
            self._read_queue = list(event.sources)
            self._read_index = 0
            assistant.reveal_search()
            assistant.search.search_finished(event.query, event.sources)
        elif isinstance(event, ToolResultEvent):
            if event.name == WEB_SEARCH_TOOL and not event.ok:
                assistant.reveal_search()
                assistant.search.search_failed(event.error or "Web search failed.")
            elif event.name == FETCH_URL_TOOL:
                self._end_read(assistant, event.ok)
        elif isinstance(event, ErrorEvent):
            assistant.add_error(event.message, event.hint)
        elif isinstance(event, Done):
            self._tokens = event.tokens_out
            self._rate = event.tokens_per_second
            assistant.finish(
                event.state.value,
                event.duration_ms or None,
                event.tokens_out,
                event.tokens_per_second,
            )
            self._sb_state = event.state.value
            self._sb_busy = False
            self._refresh_statusbar()

    def _begin_read(self, assistant: AssistantBlock) -> None:
        if self._read_index < len(self._read_queue):
            assistant.reveal_search()
            assistant.search.read_started(self._read_queue[self._read_index].url)

    def _end_read(self, assistant: AssistantBlock, ok: bool) -> None:
        if self._read_index < len(self._read_queue):
            source = self._read_queue[self._read_index]
            self._read_index += 1
            assistant.search.read_finished(source.url, ok)

    def _on_generation_done(self) -> None:
        assistant = self._assistant
        self._busy = False
        self._sb_busy = False
        if assistant is not None and not assistant.finished:
            assistant.finish("error", None)
        self._refresh_statusbar()
        self.stop_btn.configure(state="disabled")
        self.send_btn.configure(state="normal")
        self.input.focus_set()

    def _spin(self) -> None:
        if self._busy and self._assistant is not None and not self._assistant.finished:
            self._tick += 1
            self._assistant.set_tick(self._tick)
            self._refresh_statusbar()
        self.root.after(SPIN_MS, self._spin)

    def _refresh_statusbar(self) -> None:
        glyph = palette.DOT_ACTIVE if self._version else palette.DOT_IDLE
        left = f"{glyph} Ollama {self._version}" if self._version else f"{glyph} Ollama offline"
        if self.session.active_model is not None:
            left += f"   ·   {self.session.active_model.display_name}"
        self.status_left.configure(text=left)
        parts: list[str] = []
        if self._tokens is not None:
            parts.append(f"{fmt.format_tokens(self._tokens)} tok")
        rate = fmt.format_rate(self._rate)
        if rate and self._sb_busy:
            parts.append(rate)
        if self._sb_state != "idle":
            parts.append(
                fmt.status_line(
                    self._sb_state, tick=self._tick, detail=self._sb_detail,
                    active=self._sb_busy,
                )
            )
        self.status_right.configure(text="   ·   ".join(parts))

    # ------------------------------------------------------------------- dialogs

    def _show_models(self) -> None:
        models = self.session.registry.models
        win = tk.Toplevel(self.root)
        win.title("AXIOM — Models")
        win.configure(bg=palette.OBSIDIAN)
        win.transient(self.root)
        win.geometry("620x360")
        summary = f"{len(models)} model(s) reported by Ollama" if models else "No models are installed."
        _label(win, text=summary, fg=palette.MUTED).pack(fill="x", padx=12, pady=(10, 6))
        listbox = tk.Listbox(
            win, bg=palette.VOID, fg=palette.WHITE, font=FONT_SMALL, relief="flat",
            highlightthickness=1, highlightbackground=palette.GARNET_DEEP,
            selectbackground=palette.GARNET, selectforeground=palette.WHITE,
            activestyle="none",
        )
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        current = self.session.active_model.name if self.session.active_model else None
        for index, model in enumerate(models):
            caps = ", ".join(model.capabilities) if model.capabilities else "unknown"
            size = f"{model.size_gb:.2f} GB" if model.size else "?"
            marker = "●" if model.name == current else "○"
            listbox.insert(
                "end",
                f"{marker} {model.name}   ·   {model.parameter_size or '?'}   ·   {size}   ·   {caps}",
            )
            if model.name == current:
                listbox.selection_set(index)
        if not listbox.curselection() and models:
            listbox.selection_set(0)

        def choose(_event=None) -> None:
            selection = listbox.curselection()
            if not selection:
                return
            model = models[selection[0]]
            win.destroy()
            if self.session.active_model and model.name == self.session.active_model.name:
                return
            self._schedule(self._switch_model_coro(model.name))

        listbox.bind("<Double-Button-1>", choose)
        listbox.bind("<Return>", choose)

    def _show_settings(self) -> None:
        config = self.session.config
        win = tk.Toplevel(self.root)
        win.title("AXIOM — Settings")
        win.configure(bg=palette.OBSIDIAN)
        win.transient(self.root)
        win.geometry("540x480")
        frame = tk.Frame(win, bg=palette.OBSIDIAN)
        frame.pack(fill="both", expand=True, padx=14, pady=10)
        bools: dict[str, tk.BooleanVar] = {}
        for key, label in (
            ("web_search_enabled", "Web search"),
            ("show_reasoning", "Show reasoning"),
            ("reasoning_expanded", "Reasoning starts expanded"),
            ("animations", "Animations"),
            ("save_history", "Save conversation history"),
        ):
            var = tk.BooleanVar(value=getattr(config, key))
            tk.Checkbutton(
                frame, text=label, variable=var, bg=palette.OBSIDIAN, fg=palette.SILVER,
                font=FONT_SMALL, selectcolor=palette.ASH_DEEP, activebackground=palette.OBSIDIAN,
                activeforeground=palette.WHITE, relief="flat", highlightthickness=0, bd=0,
            ).pack(fill="x", pady=2, anchor="w")
            bools[key] = var
        temperature_row = tk.Frame(frame, bg=palette.OBSIDIAN)
        temperature_row.pack(fill="x", pady=(10, 2))
        _label(temperature_row, text="Temperature (0–2, empty = model default)", fg=palette.SILVER).pack(side="left")
        temperature_var = tk.StringVar(value="" if config.temperature is None else str(config.temperature))
        tk.Entry(
            temperature_row, textvariable=temperature_var, bg=palette.VOID, fg=palette.WHITE,
            insertbackground=palette.WHITE, font=FONT_SMALL, width=8, relief="flat",
            highlightthickness=1, highlightbackground=palette.ASH_DEEP,
        ).pack(side="right")
        _label(frame, text="System prompt (empty = built-in)", fg=palette.SILVER).pack(fill="x", pady=(10, 2))
        prompt_text = tk.Text(
            frame, height=6, wrap="word", bg=palette.VOID, fg=palette.WHITE,
            insertbackground=palette.WHITE, font=FONT_SMALL, relief="flat",
            highlightthickness=1, highlightbackground=palette.ASH_DEEP,
        )
        prompt_text.pack(fill="both", expand=True)
        prompt_text.insert("1.0", config.system_prompt or "")

        def save() -> None:
            for key, var in bools.items():
                setattr(config, key, var.get())
            raw = temperature_var.get().strip()
            if not raw:
                config.temperature = None
            else:
                try:
                    value = float(raw)
                except ValueError:
                    self._note("Temperature must be a number or empty.")
                    return
                if not 0.0 <= value <= 2.0:
                    self._note("Temperature must be between 0 and 2.")
                    return
                config.temperature = value
            config.system_prompt = prompt_text.get("1.0", "end-1c").strip() or None
            try:
                config.save()
            except OSError:
                pass
            self._note("Settings saved.")
            win.destroy()

        ttk.Button(frame, text="Save", command=save).pack(pady=(10, 0))

    def _show_history(self) -> None:
        if self._busy:
            self._note("Stop the current generation first.")
            return
        conversations = self.session.history()
        win = tk.Toplevel(self.root)
        win.title("AXIOM — History")
        win.configure(bg=palette.OBSIDIAN)
        win.transient(self.root)
        win.geometry("620x380")
        summary = (
            f"{len(conversations)} saved conversation(s)"
            if conversations else "No saved conversations yet."
        )
        _label(win, text=summary, fg=palette.MUTED).pack(fill="x", padx=12, pady=(10, 6))
        if not conversations:
            return
        listbox = tk.Listbox(
            win, bg=palette.VOID, fg=palette.WHITE, font=FONT_SMALL, relief="flat",
            highlightthickness=1, highlightbackground=palette.GARNET_DEEP,
            selectbackground=palette.GARNET, selectforeground=palette.WHITE,
            activestyle="none",
        )
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        for conversation in conversations:
            listbox.insert(
                "end",
                f"{fmt.history_bucket(conversation.updated_at)}   ·   "
                f"{fmt.format_clock(conversation.updated_at)}   ·   "
                f"{fmt.one_line(conversation.title or 'Untitled', 40)}",
            )
        listbox.selection_set(0)

        def selected() -> int | None:
            selection = listbox.curselection()
            return selection[0] if selection else None

        def open_conversation(_event=None) -> None:
            index = selected()
            if index is None:
                return
            conversation = conversations[index]
            win.destroy()
            loaded = self.session.load_conversation(conversation.id)
            if loaded is None:
                self._note("Could not open that conversation.")
                return
            self._render_conversation(loaded)

        def delete_conversation() -> None:
            index = selected()
            if index is None:
                return
            conversation = conversations[index]
            if self.session.delete_conversation(conversation.id):
                conversations.pop(index)
                listbox.delete(index)
                self._note("Conversation deleted.")

        buttons = tk.Frame(win, bg=palette.OBSIDIAN)
        buttons.pack(pady=(0, 10))
        ttk.Button(buttons, text="Open", command=open_conversation).pack(side="left", padx=4)
        ttk.Button(buttons, text="Delete", command=delete_conversation).pack(side="left", padx=4)
        listbox.bind("<Double-Button-1>", open_conversation)
        listbox.bind("<Return>", open_conversation)

    # --------------------------------------------------------------- lifecycle

    def _on_close(self) -> None:
        try:
            self.session.cancel()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            loop = self._loop
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(loop.stop)


def main() -> int:
    """Entry point used by ``axiom.__main__``."""
    session = ChatSession()
    app = AxiomTk(session)
    app.run()
    return 0
