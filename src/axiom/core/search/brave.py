"""Brave Search backend — a real, key-less HTML search provider.

Brave's HTML endpoint returns genuine results without an API key and, unlike
the DuckDuckGo HTML endpoint (which answers HTTP 202 with an anti-bot page),
it keeps working from a plain HTTP client. If the network is unavailable a
:class:`~axiom.core.errors.SearchUnavailableError` is raised, so the UI can
report the real failure instead of pretending.
"""

from __future__ import annotations

import html
import re

import httpx

from axiom.core.errors import SearchUnavailableError
from axiom.core.search.provider import SearchProvider, SearchResult, extract_text

#: A real desktop user agent — Brave returns the plain HTML page only for these.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

#: Brave renders each organic result inside ``<div class="snippet ...">``.
_BLOCK_RE = re.compile(r'<div class="snippet\b[^"]*"', re.IGNORECASE)
_LINK_RE = re.compile(r'<a href="(https?://[^"]+)"', re.IGNORECASE)
_TITLE_RE = re.compile(r'class="title[^"]*"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)
_SNIPPET_RE = re.compile(r'class="content[^"]*"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    text = re.sub(r"\s+", " ", _TAG_RE.sub("", fragment))
    return html.unescape(text).strip()


class BraveProvider(SearchProvider):
    """Key-less Brave Search over the public HTML endpoint."""

    name = "Brave"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = httpx.Timeout(timeout, connect=10.0)
        self._headers = {
            "User-Agent": _USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        page = await self._get("https://search.brave.com/search", {"q": query})
        results = self._parse(page)
        if not results:
            raise SearchUnavailableError(
                "Brave returned no parseable results.",
                hint="The search engine may have changed its markup or is rate limiting.",
            )
        return results[: max(1, limit)]

    @staticmethod
    def _parse(page: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen: set[str] = set()
        blocks = _BLOCK_RE.split(page)[1:]
        for block in blocks:
            link = _LINK_RE.search(block)
            title_match = _TITLE_RE.search(block)
            if link is None or title_match is None:
                continue
            url = link.group(1)
            title = _clean(title_match.group(1))
            if not title or url in seen:
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
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True, headers=self._headers
            ) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            raise SearchUnavailableError(
                "Web search is unavailable.",
                hint="Check your network connection and try again.",
            ) from exc


async def _read_page(
    timeout: httpx.Timeout, headers: dict[str, str], url: str, max_chars: int
) -> str:
    """Shared page reader used by every HTTP provider."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers=headers
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type and "text" not in content_type:
                return ""
            return extract_text(response.text, max_chars=max_chars)
    except httpx.HTTPError as exc:
        raise SearchUnavailableError(f"Could not read source: {url}") from exc
