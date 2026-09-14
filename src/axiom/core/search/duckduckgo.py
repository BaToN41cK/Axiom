"""DuckDuckGo search backend — a real, key-less HTTP search provider.

Uses the public HTML endpoints. No API keys, no simulated results: if the
network is unavailable, a :class:`~axiom.core.errors.SearchUnavailableError`
is raised and the UI reports the real failure.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from axiom.core.errors import SearchUnavailableError
from axiom.core.search.provider import SearchProvider, SearchResult, extract_text

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_LINK_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_LITE_LINK_RE = re.compile(
    r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_LITE_SNIPPET_RE = re.compile(
    r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", unquote(_TAG_RE.sub("", fragment))).strip()


def _resolve_href(href: str) -> str:
    """Resolve DuckDuckGo redirect links to their real target URL."""
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        target = query.get("uddg")
        if target:
            return target[0]
    return href


class DuckDuckGoProvider(SearchProvider):
    """Key-less DuckDuckGo HTML search."""

    name = "DuckDuckGo"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = httpx.Timeout(timeout, connect=10.0)
        self._headers = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        html = await self._post("https://html.duckduckgo.com/html/", {"q": query})
        results = self._parse(html, _LINK_RE, _SNIPPET_RE)
        if not results:
            # fall back to the lightweight endpoint
            html = await self._post("https://lite.duckduckgo.com/lite/", {"q": query})
            results = self._parse(html, _LITE_LINK_RE, _LITE_SNIPPET_RE)
        return results[: max(1, limit)]

    @staticmethod
    def _parse(html: str, link_re: re.Pattern[str], snippet_re: re.Pattern[str]) -> list[SearchResult]:
        links = link_re.findall(html)
        snippets = [_clean(s) for s in snippet_re.findall(html)]
        results: list[SearchResult] = []
        for index, (href, title_html) in enumerate(links):
            url = _resolve_href(href)
            title = _clean(title_html)
            if not url.startswith("http") or not title:
                continue
            snippet = snippets[index] if index < len(snippets) else ""
            results.append(SearchResult(title=title, url=url, snippet=snippet))
        return results

    async def fetch(self, url: str, max_chars: int = 4000) -> str:
        url = (url or "").strip()
        if not url.startswith("http"):
            raise SearchUnavailableError("Invalid URL for source reading.")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True, headers=self._headers
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    return ""
                return extract_text(response.text, max_chars=max_chars)
        except httpx.HTTPError as exc:
            raise SearchUnavailableError(f"Could not read source: {url}") from exc

    async def _post(self, url: str, data: dict[str, str]) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True, headers=self._headers
            ) as client:
                response = await client.post(url, data=data)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            raise SearchUnavailableError(
                "Web search is unavailable.",
                hint="Check your network connection and try again.",
            ) from exc
