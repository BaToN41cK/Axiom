"""Search providers: charset handling and download caps (offline tests)."""

from __future__ import annotations

import httpx
import pytest

from axiom.core.errors import SearchUnavailableError
from axiom.core.search.multi import MultiSearchProvider
from axiom.core.search.provider import SearchProvider, SearchResult, _decode_body, extract_text

WINDOWS_1251_PAGE = (
    "<html><head><meta charset=\"windows-1251\">"
    "</head><body><h1>Проверка кодировки</h1><p>Текст страницы.</p></body></html>"
).encode("windows-1251")


def _response(content: bytes, charset_header: str | None = None) -> httpx.Response:
    headers = {"content-type": f"text/html; charset={charset_header}"} if charset_header else {
        "content-type": "text/html"
    }
    return httpx.Response(200, content=content, headers=headers, request=httpx.Request("GET", "http://x"))


def test_headerless_windows_1251_page_decodes_via_meta() -> None:
    text = extract_text(_decode_body(_response(WINDOWS_1251_PAGE)))
    assert "Проверка кодировки" in text


def test_declared_utf8_is_not_touched() -> None:
    page = b"<html><body>ok</body></html>"
    assert extract_text(_decode_body(_response(page))) == "ok"


def test_header_charset_wins() -> None:
    # Body is utf-8 but the header claims koi8-r: the header must be trusted.
    page = "<html><body>байт</body></html>".encode("koi8-r")
    text = _decode_body(_response(page, charset_header="koi8-r"))
    assert "байт" in text


def test_invalid_meta_charset_falls_back() -> None:
    page = b'<html><head><meta charset="not-a-real-charset"></head><body>hi</body></html>'
    assert "hi" in _decode_body(_response(page))


# ------------------------------------------------- provider timeout plumbing


def test_multi_provider_applies_timeout_to_chain() -> None:
    chain = MultiSearchProvider(timeout=7.5)
    for provider in chain.providers:
        timeout = provider._timeout
        assert timeout.read == 7.5


# --------------------------------------------------------- fetch failure path


async def test_multi_fetch_raises_when_all_providers_fail() -> None:
    class Failing(SearchProvider):
        name = "fail"

        async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
            return []

        async def fetch(self, url: str, max_chars: int = 4000) -> str:
            raise SearchUnavailableError("nope")

    provider: MultiSearchProvider = MultiSearchProvider([Failing()])
    with pytest.raises(SearchUnavailableError):
        await provider.fetch("https://example.com")
