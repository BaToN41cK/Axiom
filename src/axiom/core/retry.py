"""Network retry utility — exponential backoff for transient failures.

Usage::

    result = await retry_async(fetch_url, args=["..."], max_attempts=3)
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from axiom.core.logging import get_logger

_LOG = get_logger("retry")

#: Default base delay in seconds.
_BASE_DELAY = 1.0
#: Default max delay cap.
_MAX_DELAY = 30.0
#: Default number of attempts.
_DEFAULT_ATTEMPTS = 3
#: HTTP / network status codes that are retryable.
_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}


@dataclass
class RetryResult:
    """Result of a retried operation."""
    ok: bool
    value: Any = None
    error: str | None = None
    attempts: int = 0


def is_retryable_error(exc: Exception) -> bool:
    """Check if an exception represents a transient failure.

    The cause chain is walked: search providers wrap transport errors into
    ``SearchUnavailableError ... from exc``, and the underlying ``httpx``
    error is the part that says whether a retry can help.
    """
    import httpx

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        # TransportError covers connect/read/write errors and protocol breaks —
        # exactly what a VPN switch does to in-flight requests; TimeoutException
        # covers connect/read/write timeouts.
        if isinstance(current, (TimeoutError, ConnectionError,
                               httpx.TimeoutException, httpx.TransportError)):
            return True
        if isinstance(current, httpx.HTTPStatusError):
            return current.response.status_code in _RETRYABLE_STATUSES
        current = current.__cause__ or current.__context__
    return False


async def retry_async(
    func: Callable[..., Awaitable[Any]],
    *,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    max_attempts: int = _DEFAULT_ATTEMPTS,
    base_delay: float = _BASE_DELAY,
    max_delay: float = _MAX_DELAY,
    retryable: Callable[[Exception], bool] = is_retryable_error,
) -> RetryResult:
    """Execute *func* with exponential backoff retry.

    Only retries errors for which *retryable* returns True.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await func(*(args or []), **(kwargs or {}))
            if attempt > 1:
                _LOG.info("Retry attempt %d/%d succeeded", attempt, max_attempts)
            return RetryResult(ok=True, value=result, attempts=attempt)
        except Exception as exc:
            last_error = exc
            if not retryable(exc):
                _LOG.debug("Non-retryable error: %s", exc)
                return RetryResult(ok=False, error=str(exc), attempts=attempt)
            if attempt < max_attempts:
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                _LOG.warning(
                    "Attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt, max_attempts, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                _LOG.error("All %d attempts failed: %s", max_attempts, exc)

    return RetryResult(
        ok=False,
        error=str(last_error) if last_error else "Unknown error",
        attempts=max_attempts,
    )
