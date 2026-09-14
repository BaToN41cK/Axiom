"""Search abstraction shared by all search backends."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

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

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Run a real search and return structured results."""

    @abstractmethod
    async def fetch(self, url: str, max_chars: int = 4000) -> str:
        """Fetch a page and return its readable text (for source reading)."""


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