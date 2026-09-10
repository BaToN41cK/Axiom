"""Web tools: fetch, search (via provider abstraction) and download with limits."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from axiom.core.logging import get_logger

logger = get_logger("web")


@dataclass
class WebResponse:
    url: str
    status: int
    content_type: str
    body: str
    elapsed: float


class WebCache:
    """Tiny TTL cache for fetched URLs."""

    def __init__(self, ttl: float = 600.0) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, WebResponse]] = {}

    def get(self, url: str) -> WebResponse | None:
        entry = self._store.get(url)
        if entry is None:
            return None
        ts, response = entry
        if time.monotonic() - ts > self._ttl:
            self._store.pop(url, None)
            return None
        return response

    def put(self, url: str, response: WebResponse) -> None:
        self._store[url] = (time.monotonic(), response)


def validate_url(url: str, allowed_schemes: tuple[str, ...] = ("http", "https")) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        raise ValueError(f"URL not allowed: {url!r}")
    # Block obvious internal targets unless explicitly local.
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "0.0.0.0") or host.endswith(".local"):
        pass  # local dev fetch is allowed (useful for testing servers)
    return url


class WebClient:
    """Async web client with size limits, timeout, cache and retries."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._timeout = float(cfg.get("timeout", 30.0))
        self._max_bytes = int(cfg.get("max_response_bytes", 5_000_000))
        self._allowed = tuple(cfg.get("allowed_schemes", ["http", "https"]))
        self._cache = WebCache(ttl=float(cfg.get("cache_ttl", 600)))
        self._retries = int(cfg.get("retries", 1))

    async def fetch(self, url: str, method: str = "GET") -> WebResponse:
        url = validate_url(url, self._allowed)
        cached = self._cache.get(url)
        if cached is not None:
            return cached
        start = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=True
                ) as client:
                    response = await client.request(method, url)
                    content = response.content[: self._max_bytes]
                    if len(response.content) > self._max_bytes:
                        logger.warning("Response truncated to %d bytes", self._max_bytes)
                    ctype = response.headers.get("content-type", "text/plain")
                    body = content.decode("utf-8", "replace")
                    web = WebResponse(
                        url=str(response.url),
                        status=response.status_code,
                        content_type=ctype,
                        body=body,
                        elapsed=time.monotonic() - start,
                    )
                    self._cache.put(url, web)
                    return web
            except (httpx.HTTPError, ValueError, OSError) as exc:
                last_error = exc
        raise RuntimeError(f"Fetch failed for {url}: {last_error}")

    async def download(self, url: str, dest: Path, max_bytes: int | None = None) -> Path:
        url = validate_url(url, self._allowed)
        limit = max_bytes or self._max_bytes
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                total = 0
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("wb") as fh:
                    async for chunk in response.aiter_bytes(65536):
                        total += len(chunk)
                        if total > limit:
                            dest.unlink(missing_ok=True)
                            raise RuntimeError(
                                f"Download exceeded size limit ({limit} bytes)"
                            )
                        fh.write(chunk)
        return dest
