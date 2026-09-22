"""Modal panels — models, history, settings, help and real system status.

Every panel is a *projection* of core state: model rows come from
:class:`~axiom.core.models.ModelRegistry`, history rows from the real
:class:`~axiom.core.history.HistoryStore`, and the status panel prints the live
Ollama URL, the model that is actually selected and the capabilities Ollama
reported (``unknown`` when it reported nothing — never an optimistic guess).

All panels share one shape: a titled frame, an arrow-navigable body and a
result delivered back to :mod:`axiom.frontends.tui.app` through ``dismiss``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    OptionList,
    Static,
    Switch,
    TextArea,
)
from textual.widgets.option_list import Option

from axiom.core.config import Config
from axiom.core.history import Conversation
from axiom.core.models import ModelInfo
from axiom.shared import formatting as fmt
from axiom.shared import theme

#: Capabilities Ollama may report; anything else is shown as ``unknown``.
CAPABILITIES = ("completion", "tools", "thinking", "vision")


def capability_state(model: ModelInfo, capability: str) -> str:
    """``supported`` / ``unsupported`` / ``unknown`` — as really reported."""
    state = model.supports(capability)
    if state is True:
        return "supported"
    if state is False:
        return "unsupported"
    return "unknown"


def capability_glyph(model: ModelInfo, capability: str) -> str:
    state = model.supports(capability)
    if state is True:
        return theme.TICK
    if state is False:
        return theme.CROSS
    return theme.BULLET


def capability_text(model: ModelInfo, separator: str = "  ") -> str:
    """Compact capability line — never claims more than Ollama reported."""
    return separator.join(f"{capability_glyph(model, c)} {c}" for c in CAPABILITIES)


def model_option(model: ModelInfo, current: str | None) -> Option:
    """One model row: display name, size, quantization and capabilities."""
    marker = theme.ARROW if model.name == current else " "
    size = f"{model.size_gb:.2f} GB" if model.size else "—"
    quant = model.quantization or "—"
    params = model.parameter_size or "—"
    prompt = (
        f"{marker} {model.display_name}  ·  {params}  ·  {size}  ·  {quant}\n"
        f"    {model.name}   {capability_text(model)}"
    )
    return Option(prompt, id=model.name)


class PanelScreen(ModalScreen):
    """Base modal panel: titled frame, scrolling body, ``esc`` to close."""

    BINDINGS = [
        Binding("escape", "close_panel", "Close", show=True),
        Binding("f2", "close_panel", "Close", show=False),
    ]

    #: Frame title (overridden by subclasses).
    title_text = "PANEL"

    def body(self) -> ComposeResult:
        """Yield the panel contents (subclasses must implement this)."""
        raise NotImplementedError

    def keys_hint(self) -> str:
        """Right-hand side of the frame border."""
        return "esc  close"

    def subtitle_lines(self) -> list[str]:
        """Optional real facts printed under the frame title."""
        return []

    def compose(self) -> ComposeResult:
        frame = Vertical(classes="panel")
        frame.border_title = self.title_text
        frame.border_subtitle = self.keys_hint()
        with frame:
            subtitle = "\n".join(line for line in self.subtitle_lines() if line)
            if subtitle:
                yield Static(subtitle, classes="panel-subtitle", markup=False)
            with VerticalScroll(id="panel-body"):
                yield from self.body()

    def action_close_panel(self) -> None:
        self.dismiss(None)


class ModelPanel(PanelScreen):
    """``/models`` — the real Ollama model list; Enter switches the model."""

    title_text = "MODELS"

    def __init__(
        self,
        models: list[ModelInfo],
        current: str | None,
        *,
        refresh: Callable[[], Awaitable[list[ModelInfo]]] | None = None,
    ) -> None:
        super().__init__()
        self._models = list(models)
        self._current = current
        self._refresh_callback = refresh

    BINDINGS = [Binding("r", "refresh_models", "Refresh", show=False)]

    async def action_refresh_models(self) -> None:
        """Re-read the real model list from Ollama."""
        if self._refresh_callback is None:
            return
        try:
            self._models = list(await self._refresh_callback())
        except Exception:
            return
        option_list = self.query_one("#model-list", OptionList)
        option_list.clear_options()
        for model in self._models:
            option_list.add_option(model_option(model, self._current))
        for index, model in enumerate(self._models):
            if model.name == self._current:
                option_list.highlighted = index
                break

    def keys_hint(self) -> str:
        hint = "↑↓ navigate   ·   enter switch   ·   esc close"
        if self._refresh_callback is not None:
            hint = "r refresh   ·   " + hint
        return hint

    def subtitle_lines(self) -> list[str]:
        if not self._models:
            return ["No models are installed in Ollama."]
        marker = "selected" if self._current else "none selected"
        return [f"{len(self._models)} model(s) reported by Ollama   ·   {marker}"]

    def body(self) -> ComposeResult:
        options = [model_option(model, self._current) for model in self._models]
        option_list = OptionList(*options, id="model-list")
        yield option_list

    def on_mount(self) -> None:
        option_list = self.query_one("#model-list", OptionList)
        for index, model in enumerate(self._models):
            if model.name == self._current:
                option_list.highlighted = index
                break
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(str(event.option.id))


class HelpPanel(PanelScreen):
    """``/help`` — the command reference plus navigation basics."""

    title_text = "HELP"

    def __init__(self, commands) -> None:
        super().__init__()
        self._commands = list(commands)

    def keys_hint(self) -> str:
        return "↑↓ scroll   ·   esc close"

    def subtitle_lines(self) -> list[str]:
        return [
            "Type / in the prompt to open the command menu — Tab or Enter completes,",
            "↑↓ navigate, Esc dismisses. Sources and titles are clickable with the mouse.",
        ]

    def body(self) -> ComposeResult:
        widest = max((len(command.usage) for command in self._commands), default=8)
        yield OptionList(
            *[
                Option(f"  {command.usage.ljust(widest)}  {command.description}", disabled=True)
                for command in self._commands
            ],
            id="help-list",
        )
        yield Static(
            "\n".join(
                [
                    "Enter          send message (in the prompt)",
                    "Ctrl+J         newline inside the prompt",
                    "Ctrl+C         stop the running generation",
                    "Ctrl+Q         quit AXIOM",
                    "Mouse wheel    scroll chat, reasoning and sources",
                    "Click Stop     cancel the current generation",
                ]
            ),
            classes="panel-note",
            markup=False,
        )


class HistoryPanel(PanelScreen):
    """``/history`` — saved conversations; Enter opens, ``d`` deletes."""

    title_text = "HISTORY"
    BINDINGS = [Binding("d", "delete_conversation", "Delete", show=False)]

    def __init__(
        self,
        conversations: list[Conversation],
        *,
        on_delete: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__()
        self._conversations = list(conversations)
        self._on_delete = on_delete

    def keys_hint(self) -> str:
        return "↑↓ navigate   ·   enter open   ·   d delete   ·   esc close"

    def subtitle_lines(self) -> list[str]:
        if not self._conversations:
            return ["No saved conversations yet."]
        return [f"{len(self._conversations)} saved conversation(s)"]

    def body(self) -> ComposeResult:
        yield OptionList(id="history-list")

    def on_mount(self) -> None:
        self._rebuild()
        option_list = self.query_one("#history-list", OptionList)
        if option_list.option_count:
            option_list.focus()

    def _rebuild(self) -> None:
        option_list = self.query_one("#history-list", OptionList)
        option_list.clear_options()
        bucket: str | None = None
        for conversation in self._conversations:
            current_bucket = fmt.history_bucket(conversation.updated_at)
            if current_bucket != bucket:
                bucket = current_bucket
                option_list.add_option(Option(f" {bucket.upper()}", disabled=True))
            stamp = fmt.format_clock(conversation.updated_at)
            title = fmt.one_line(conversation.title or "Untitled", 46)
            option_list.add_option(Option(f"   {stamp}  {title}", id=conversation.id))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            event.stop()
            self.dismiss(str(event.option.id))

    def action_delete_conversation(self) -> None:
        option_list = self.query_one("#history-list", OptionList)
        if option_list.highlighted is None:
            return
        option = option_list.get_option_at_index(option_list.highlighted)
        if not option.id or option.disabled:
            return
        conversation_id = str(option.id)
        deleted = self._on_delete(conversation_id) if self._on_delete is not None else False
        if deleted:
            self._conversations = [
                conversation for conversation in self._conversations if conversation.id != conversation_id
            ]
            self._rebuild()


_BOOL_SETTINGS: tuple[tuple[str, str, str], ...] = (
    ("switch-search", "web_search_enabled", "Web search"),
    ("switch-reasoning", "show_reasoning", "Show reasoning (when provided)"),
    ("switch-expanded", "reasoning_expanded", "Reasoning starts expanded"),
    ("switch-animations", "animations", "Animations"),
    ("switch-history", "save_history", "Save conversation history"),
)

_THINK_OPTIONS: tuple[tuple[str, str], ...] = (
    ("think-auto", "Thinking: auto (follow model capability)"),
    ("think-on", "Thinking: on (always request)"),
    ("think-off", "Thinking: off (never request)"),
)


class SettingsPanel(PanelScreen):
    """``/settings`` — live edits of the real configuration, saved on change."""

    title_text = "SETTINGS"

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    def keys_hint(self) -> str:
        return "↑↓ navigate   ·   enter save   ·   esc close"

    def subtitle_lines(self) -> list[str]:
        direct = self._config.system_prompt or "(model default)"
        if self._config.think is None:
            think = "auto"
        elif self._config.think:
            think = "on"
        else:
            think = "off"
        web = "on" if self._config.web_search_enabled else "off"
        return [
            f"Model {self._config.model or '(auto)'}  ·  {self._config.ollama_url}",
            f"Web {web}  ·  Thinking {think}  ·  Theme {self._config.theme}",
            f"Prompt: {direct[:64]}",
        ]

    def body(self) -> ComposeResult:
        for switch_id, field_name, label in _BOOL_SETTINGS:
            with Horizontal(classes="settings-row"):
                yield Static(label, classes="settings-label", markup=False)
                yield Switch(getattr(self._config, field_name), id=switch_id)
        yield Static("Thinking mode (Ollama think flag)", classes="settings-label", markup=False)
        yield OptionList(
            *[Option(label, id=option_id) for option_id, label in _THINK_OPTIONS],
            id="think-list",
        )
        with Horizontal(classes="settings-row"):
            yield Static("Ollama URL", classes="settings-label", markup=False)
            yield Input(value=self._config.ollama_url, id="ollama-input")
        with Horizontal(classes="settings-row"):
            yield Static("Model (empty = auto)", classes="settings-label", markup=False)
            yield Input(
                value="" if not self._config.model else self._config.model,
                placeholder="qwen3:8b",
                id="model-input",
            )
        with Horizontal(classes="settings-row"):
            yield Static("Temperature", classes="settings-label", markup=False)
            yield Input(
                value="" if self._config.temperature is None else str(self._config.temperature),
                placeholder="auto",
                id="temperature-input",
            )
        yield Static("System prompt", classes="settings-label", markup=False)
        yield TextArea(self._config.system_prompt or "", id="system-prompt-input")
        yield Button("Save", id="save-settings", variant="default")

    def on_mount(self) -> None:
        current = (
            "think-auto" if self._config.think is None else ("think-on" if self._config.think else "think-off")
        )
        option_list = self.query_one("#think-list", OptionList)
        for index, option in enumerate(option_list._options):
            if option.id == current:
                option_list.highlighted = index
                break

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = str(event.option.id or "")
        if option_id == "think-auto":
            self._config.think = None
        elif option_id == "think-on":
            self._config.think = True
        elif option_id == "think-off":
            self._config.think = False
        else:
            return
        self._save()
        if self.app is not None:
            self.app.notify("Thinking mode saved.", title="Settings", timeout=3)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        for switch_id, field_name, _ in _BOOL_SETTINGS:
            if event.switch.id == switch_id:
                setattr(self._config, field_name, event.value)
                self._save()
                return

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "temperature-input":
            self._apply_temperature(event.input.value)
        elif event.input.id == "model-input":
            self._config.model = event.input.value.strip() or None
            self._save()
        elif event.input.id == "ollama-input":
            self._config.ollama_url = event.input.value.strip() or self._config.ollama_url
            self._save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save-settings":
            return
        self._apply_temperature(self.query_one("#temperature-input", Input).value)
        self._config.model = self.query_one("#model-input", Input).value.strip() or None
        self._config.ollama_url = self.query_one("#ollama-input", Input).value.strip() or self._config.ollama_url
        self._config.system_prompt = self.query_one("#system-prompt-input", TextArea).text.strip() or None
        self._save()
        if self.app is not None:
            self.app.notify("Settings saved.", title="Settings", timeout=3)

    def _apply_temperature(self, raw: str) -> None:
        raw = raw.strip()
        if not raw:
            self._config.temperature = None
            self._save()
            return
        try:
            value = float(raw)
        except ValueError:
            if self.app is not None:
                self.app.notify("Temperature must be a number or empty.", severity="warning", timeout=4)
            return
        if not 0.0 <= value <= 2.0:
            if self.app is not None:
                self.app.notify("Temperature must be between 0 and 2.", severity="warning", timeout=4)
            return
        self._config.temperature = value
        self._save()

    def _save(self) -> None:
        try:
            self._config.save()
        except OSError:
            pass  # persistence must never break the panel


class ProfilePanel(PanelScreen):
    """``/profiles`` — system prompt profile selector.

    Shows all profiles with a marker for the currently active one.
    Arrow keys to navigate, Enter to select, Escape to close.
    """

    title_text = "PROFILES"

    def __init__(
        self,
        profiles: dict[str, str],
        active: str,
        *,
        on_select: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self._profiles = profiles
        self._active = active
        self._on_select = on_select

    def keys_hint(self) -> str:
        past = [f"✓ {self._active}"]
        return " ↑↓  select  ·  " + "  ".join(past) + "  ·  esc  close"

    def subtitle_lines(self) -> list[str]:
        return [f"Active: {theme.ARROW} {self._active}"]

    def body(self) -> ComposeResult:
        yield Static(f"Active profile: {self._active}", id="profile-current", markup=False)
        with OptionList(id="profile-list"):
            for name, prompt in self._profiles.items():
                glyph = theme.ARROW if name == self._active else " "
                label = f"{glyph} {name}"
                # Truncate prompt preview to first line
                preview = prompt.split("\n")[0][:80]
                if len(prompt.split("\n")[0]) > 80:
                    preview += "…"
                rows = Option(f"{label}\n    {preview}", id=name)
                yield rows

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        name = str(event.option.id) if event.option.id else ""
        if name and name in self._profiles:
            self.dismiss(name)
        else:
            if self.app is not None:
                self.app.notify(f"Unknown profile: {name}", severity="warning", timeout=3)


class StatusPanel(PanelScreen):
    """``/status`` — real system status: server, model, capabilities, metrics."""

    title_text = "STATUS"

    def __init__(
        self,
        *,
        ollama_url: str,
        version: str | None,
        model: ModelInfo | None,
        metrics: dict,
    ) -> None:
        super().__init__()
        self._ollama_url = ollama_url
        self._version = version
        self._model = model
        self._metrics = dict(metrics)

    def keys_hint(self) -> str:
        return "esc close"

    def subtitle_lines(self) -> list[str]:
        server = self._ollama_url + (f"   ·   version {self._version}" if self._version else "")
        return [server]

    def body(self) -> ComposeResult:
        connected = "connected" if self._version else "unknown (splash probe)"
        thinking = self._model.supports("thinking") if self._model else None
        thinking_text = (
            "available" if thinking is True else ("unavailable" if thinking is False else "unknown")
        )
        rows: list[tuple[str, str]] = [
            ("Ollama", f"{theme.DOT_ACTIVE} {connected}" if self._version else f"{theme.DOT_IDLE} {connected}"),
            ("Endpoint", self._ollama_url),
            ("Model", self._model.name if self._model else "none"),
            ("Streaming", "on (NDJSON deltas)"),
            ("Reasoning", thinking_text),
            ("Web Search", "available (DuckDuckGo, key-less)"),
        ]
        if self._model is not None:
            rows.append(("Label", self._model.display_name))
            rows.append(("Capabilities", capability_text(self._model)))
            rows.append(("Parameters", self._model.parameter_size or "unknown"))
            rows.append(("Quantization", self._model.quantization or "unknown"))
            rows.append(("Size", f"{self._model.size_gb:.2f} GB" if self._model.size else "unknown"))
        metrics = self._metrics
        duration = fmt.format_duration_ms(metrics.get("duration_ms"))
        if duration:
            rows.append(("Last generation", duration))
        tokens_in = metrics.get("tokens_in")
        if tokens_in is not None:
            rows.append(("Tokens in", fmt.format_tokens(tokens_in)))
        tokens_out = metrics.get("tokens_out")
        if tokens_out is not None:
            rows.append(("Tokens out", fmt.format_tokens(tokens_out)))
        rate = fmt.format_rate(metrics.get("tokens_per_second") or None)
        if rate:
            rows.append(("Throughput", rate))
        with Vertical():
            for key, value in rows:
                with Horizontal(classes="status-row"):
                    yield Static(key, classes="status-key", markup=False)
                    yield Static(value, classes="status-value", markup=False)
