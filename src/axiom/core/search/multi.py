"""Multi-engine search chain — the real internet access of AXIOM.

No single key-less search endpoint is reliable forever: DuckDuckGo now answers
plain HTTP clients with an anti-bot page, while Brave's HTML endpoint keeps
serving real results. AXIOM therefore tries a *chain* of real providers and
returns the first one that actually produced results, remembering which engine
answered so the UI can report it truthfully.

    Brave  →  DuckDuckGo  →  Wikipedia

If every provider fails, the original :class:`SearchUnavailableError` is raised:
the UI then shows "Search unavailable" instead of inventing an answer.
"""

from __future__ import annotations

import httpx

from axiom.core.errors import SearchUnavailableError
from axiom.core.search.brave import BraveProvider
from axiom.core.search.duckduckgo import DuckDuckGoProvider
from axiom.core.search.provider import SearchProvider, SearchResult
from axiom.core.search.wikipedia import WikipediaProvider


def default_chain() -> list[SearchProvider]:
    """The providers AXIOM tries, in order of usefulness."""
    return [BraveProvider(), DuckDuckGoProvider(), WikipediaProvider()]


class MultiSearchProvider(SearchProvider):
    """Runs a chain of real providers and reports which one answered."""

    name = "Web"

    #: Ceiling on raw page download, independent of the context trim.
    MAX_DOWNLOAD_CHARS = 3_000_000

    def __init__(self, providers: list[SearchProvider] | None = None, timeout: float | None = None) -> None:
        self._providers = list(providers) if providers else default_chain()
        if timeout is not None and timeout > 0:
            for provider in self._providers:
                # Every built-in provider stores its httpx.Timeout as _timeout.
                setter = getattr(provider, "_apply_timeout", None)
                if setter is not None:
                    setter(timeout)
                elif hasattr(provider, "_timeout"):
                    provider._timeout = httpx.Timeout(timeout, connect=min(10.0, timeout))
        #: Name of the provider that produced the last successful search.
        self.last_provider: str = ""
        #: Real errors of every provider that failed during the last search.
        self.last_errors: list[str] = []

    @property
    def providers(self) -> list[SearchProvider]:
        return list(self._providers)

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        self.last_provider = ""
        self.last_errors = []
        for provider in self._providers:
            try:
                results = await provider.search(query, limit=limit)
            except SearchUnavailableError as exc:
                self.last_errors.append(f"{provider.name}: {exc}")
                continue
            except Exception as exc:
                self.last_errors.append(f"{provider.name}: {type(exc).__name__}: {exc}")
                continue
            if results:
                self.last_provider = provider.name
                return results
            self.last_errors.append(f"{provider.name}: no results")
        reason = "; ".join(self.last_errors[:3]) or "no provider returned results"
        raise SearchUnavailableError(
            "Web search is unavailable.",
            hint=f"Tried {len(self._providers)} engines — {reason}",
        )

    async def fetch(self, url: str, max_chars: int = 4000) -> str:
        """Read a page with the first provider that succeeds.

        The raw download is capped (``MAX_DOWNLOAD_CHARS``) before HTML is
        turned into text, so huge pages cannot blow up memory; the text itself
        is still trimmed to ``max_chars``.
        """
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                text = await provider.fetch(url, max_chars=self.MAX_DOWNLOAD_CHARS)
            except SearchUnavailableError as exc:
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                continue
            return text[:max_chars].rstrip() + "…" if len(text) > max_chars else text
        raise SearchUnavailableError(
            f"Could not read source: {url}",
            hint=str(last_error) if last_error else None,
        )
