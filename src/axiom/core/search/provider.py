"""Search abstraction shared by all search backends."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel


class SearchResult(BaseModel):
    """One web search result."""

    title: str
    url: str
    snippet: str = ""


class SearchProvider(ABC):
    """Interface every search backend must implement.

    The UI never talks to a backend directly — it only receives structured
    :class:`SearchResult` items through the core event stream.
    """

    #: human readable name shown in the UI
    name: str = "search"

    #: httpx timeout used by providers doing real HTTP. Declared on the base so
    #: MultiSearchProvider can retune it across the whole chain.
    _timeout: httpx.Timeout = httpx.Timeout(20.0, connect=10.0)

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Run a real search and return structured results."""

    @abstractmethod
    async def fetch(self, url: str, max_chars: int = 4000) -> str:
        """Fetch a page and return its readable text (for source reading)."""


def _decode_body(response: httpx.Response) -> str:
    """Decode a response body honouring ``<meta charset>``.

    ``httpx`` (like ``requests``) trusts only the HTTP header; for header-less
    pages it falls back to the default encoding and windows-1251 sites turn
    into mojibake. The bytes are re-decoded using the charset declared in the
    HTML itself when present and valid.
    """
    if response.encoding is not None and response.encoding.lower() not in ("ascii", "utf-8"):
        # Header already declared a non-UTF8 encoding — trust it.
        return response.text
    data = response.content
    try:
        text = data.decode(response.encoding or "utf-8")
    except (UnicodeDecodeError, LookupError):
        text = data.decode("utf-8", errors="replace")
    if "\ufffd" not in text:
        return text
    match = re.search(
        rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""", data[:4096], re.IGNORECASE
    )
    if not match:
        return text
    try:
        return data.decode(match.group(1).decode("ascii"))
    except (UnicodeDecodeError, LookupError):
        return text


def extract_text(html: str, max_chars: int = 4000) -> str:
    """Very small, dependency-free HTML-to-text converter.

    Removes scripts/styles/tags, decodes the most common entities and
    collapses whitespace. Used for reading search sources.
    """
    text = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    entities = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
        "&mdash;": "—",
        "&ndash;": "–",
        "&hellip;": "…",
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    text = re.sub(r"&#x?[0-9a-fA-F]+;", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text
