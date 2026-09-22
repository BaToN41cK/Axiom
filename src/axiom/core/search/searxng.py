"""SearXNG metasearch backend — regional resilience for the search chain.

Brave and DuckDuckGo are unreachable from a number of countries and
networks; SearXNG is an open metasearch engine whose public instances
aggregate many engines and require neither keys nor JavaScript. AXIOM tries
a small list of instances — the first one that returns parseable results
wins — so a single blocked or rate-limited instance cannot take the whole
chain down.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

import httpx

from axiom.core.errors import SearchUnavailableError
from axiom.core.search.brave import _read_page
from axiom.core.search.provider import SearchProvider, SearchResult

#: Public instances that serve results to plain HTTP clients without a JS
#: challenge. Ordered by observed reliability; a dead, blocked or rate-limited
#: (HTTP 429) instance is simply skipped by the chain. Many instances only
#: accept POST searches (bot mitigation), so requests are POSTed by default.
_INSTANCES = (
    "https://opnxng.com",
    "https://searx.tiekoetter.com",
    "https://priv.au",
    "https://searx.be",
    "https://search.inetol.net",
)

#: SearXNG renders every organic result inside ``<article class="result ...">``
#: with the URL in ``<a href>`` inside ``h3`` and the snippet in a ``p``.
_BLOCK_RE = re.compile(r'<article[^>]+class="[^"]*\bresult\b[^"]*"', re.IGNORECASE)
_LINK_RE = re.compile(r'<h3[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_SNIPPET_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _clean(fragment: str) -> str:
    text = re.sub(r"\s+", " ", _TAG_RE.sub("", fragment))
    return html.unescape(text).strip()


class SearXNGProvider(SearchProvider):
    """Key-less metasearch over public SearXNG instances."""

    name = "SearXNG"

    def __init__(self, timeout: float = 20.0, instances: tuple[str, ...] = _INSTANCES) -> None:
        self._timeout = httpx.Timeout(timeout, connect=10.0)
        self._instances = tuple(instances)
        self._headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        errors: list[str] = []
        for base in self._instances:
            url = f"{base.rstrip('/')}/search"
            try:
                page = await self._get(url, {"q": query})
            except SearchUnavailableError as exc:
                errors.append(f"{base}: {exc}")
                continue
            results = self._parse(page, base)
            if results:
                return results[: max(1, limit)]
            errors.append(f"{base}: no results")
        raise SearchUnavailableError(
            "SearXNG search is unavailable.",
            hint="; ".join(errors[:3]) or "no instance returned results",
        )

    @staticmethod
    def _parse(page: str, base: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen: set[str] = set()
        blocks = _BLOCK_RE.split(page)[1:]
        for block in blocks:
            match = _LINK_RE.search(block)
            if match is None:
                continue
            raw_url, title_html = match.group(1), match.group(2)
            url = urljoin(base, raw_url)
            title = _clean(title_html)
            host = urlparse(url).netloc
            # Instance-internal links are not real search results.
            if not title or not host or host in {urlparse(base).netloc, "searx", ""}:
                continue
            if url in seen:
                continue
            snippet_match = _SNIPPET_RE.search(block)
            seen.add(url)
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=_clean(snippet_match.group(1)) if snippet_match else "",
                )
            )
        return results

    async def fetch(self, url: str, max_chars: int = 4000) -> str:
        url = (url or "").strip()
        if not url.startswith("http"):
            raise SearchUnavailableError("Invalid URL for source reading.")
        return await _read_page(self._timeout, self._headers, url, max_chars)

    async def _get(self, url: str, params: dict[str, str]) -> str:
        """POST the query — most instances reject GET /search as bot traffic.

        A 405 answer means the instance wants GET after all; it is retried
        that way before the instance is given up on.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True, headers=self._headers
            ) as client:
                response = await client.post(url, data=params)
                if response.status_code in (404, 405):
                    response = await client.get(url, params=params)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            raise SearchUnavailableError(
                f"Instance unreachable: {urlparse(url).netloc}",
                hint="The instance may be blocked, rate-limited or down.",
            ) from exc
