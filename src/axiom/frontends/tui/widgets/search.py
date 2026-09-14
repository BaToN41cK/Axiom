"""Web-search block — every line comes from real tool events."""

from __future__ import annotations

from textual.containers import Container
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from axiom.core.events import SourceItem
from axiom.shared import formatting as fmt
from axiom.shared import theme


class SourceRow(ListItem):
    """One clickable/selectable search source."""

    class Opened(Message):
        def __init__(self, source: SourceItem) -> None:
            self.source = source
            super().__init__()

    def __init__(self, source: SourceItem, compact: bool = False) -> None:
        super().__init__(classes="source-row")
        self.source = source
        self._compact = compact

    def compose(self):
        number = f"{self.source.index:02d}"
        title = fmt.truncate(self.source.title or self.source.url, 90)
        yield Static(f"{number}  {title}", classes="source-title", markup=False)
        if not self._compact and self.source.url:
            yield Static(f"    {self.source.url}", classes="source-url", markup=False)

    def on_click(self) -> None:
        self.post_message(self.Opened(self.source))


class WebSearchPanel(Container):
    """Search steps plus the real source list."""

    def __init__(self, *, animations: bool = True) -> None:
        super().__init__(classes="search-panel")
        self._animations = animations
        self._tick = 0
        self._query = ""
        self._searching = False
        self._sources: list[SourceItem] = []
        self._reading: dict[str, str] = {}
        self._read_done = 0
        self._read_failed = 0
        self._error: str | None = None
        self._timer = None

    def compose(self):
        yield Static("WEB SEARCH", classes="block-label")
        yield Static("", id="search-steps", markup=False)
        yield ListView(id="search-sources")

    def on_mount(self) -> None:
        if self._animations:
            self._timer = self.set_interval(theme.SPINNER_INTERVAL, self._animate_steps)

    # ------------------------------------------------------------------ events

    def search_started(self, query: str) -> None:
        self._query = query
        self._searching = True
        self._refresh()

    def search_finished(self, query: str, sources: list[SourceItem]) -> None:
        self._query = query or self._query
        self._searching = False
        self._sources = list(sources)
        source_list = self.query_one("#search-sources", ListView)
        source_list.clear()
        for source in self._sources:
            source_list.append(SourceRow(source, compact=len(self._sources) > 6))
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

    def finish(self, *, cancelled: bool = False) -> None:
        self._searching = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._refresh()

    @property
    def sources(self) -> list[SourceItem]:
        return list(self._sources)

    # ----------------------------------------------------------------- private

    def _animate_steps(self) -> None:
        if self._searching or any(v == "active" for v in self._reading.values()):
            self._tick += 1
            self._refresh()

    def _refresh(self) -> None:
        try:
            steps = self.query_one("#search-steps", Static)
        except Exception:  # pragma: no cover - not composed yet
            return
        lines: list[str] = []
        if self._error and not self._sources:
            lines.append(f"{theme.CROSS} Search  {self._error}")
        elif self._searching:
            lines.append(f"{fmt.spinner_frame(self._tick)} Searching  {fmt.truncate(self._query, 70)}")
        elif self._sources:
            lines.append(
                f"{theme.TICK} Search  {fmt.truncate(self._query, 60)}  ·  {len(self._sources)} sources"
            )
        elif self._query:
            lines.append(f"{theme.CROSS} Search  {fmt.truncate(self._query, 70)}  ·  no results")

        active_reads = sum(1 for v in self._reading.values() if v == "active")
        total_reads = self._read_done + self._read_failed + active_reads
        if total_reads:
            if active_reads:
                lines.append(f"{fmt.spinner_frame(self._tick)} Reading sources  ·  {self._read_done}/{total_reads}")
            else:
                failed = f"  ·  {self._read_failed} failed" if self._read_failed else ""
                lines.append(f"{theme.TICK} Reading sources  ·  {self._read_done}/{total_reads}{failed}")
        steps.update("\n".join(lines))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, SourceRow):
            self.post_message(SourceRow.Opened(event.item.source))