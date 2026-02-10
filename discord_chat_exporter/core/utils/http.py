"""Shared httpx client configuration and retry pipeline using tenacity."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    retry_if_result,
    stop_after_attempt,
)

logger = logging.getLogger(__name__)

# Status codes that should trigger a retry.
_RETRYABLE_STATUS_CODES = frozenset({
    429,  # Too Many Requests
    408,  # Request Timeout
})


def _is_retryable_status(status_code: int) -> bool:
    """Return True if the HTTP status code should trigger a retry."""
    return status_code in _RETRYABLE_STATUS_CODES or status_code >= 500


def _is_retryable_response(response: httpx.Response) -> bool:
    """Tenacity retry predicate: retry on retryable HTTP status codes."""
    return _is_retryable_status(response.status_code)


def _is_retryable_exception(exc: BaseException) -> bool:
    """Tenacity retry predicate: retry on transient network/timeout errors."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return _is_retryable_status(exc.response.status_code)
    return False


def _compute_retry_wait(retry_state: RetryCallState) -> float:
    """Custom wait callback that respects the Retry-After header on 429 responses.

    Falls back to exponential backoff (2^attempt + 1 seconds) otherwise.
    """
    outcome = retry_state.outcome
    if outcome is not None and not outcome.failed:
        response: httpx.Response = outcome.result()
        # Use Retry-After header if the server sent one (rate-limit scenario).
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                delay = float(retry_after) + 1.0  # small buffer
                return delay
            except (ValueError, TypeError):
                pass

    # Exponential backoff: 2^attempt + 1
    attempt = retry_state.attempt_number
    return float(2**attempt + 1)


# ---- Retry decorator for response-level retries ----
# Used by DiscordClient._request to retry on 429/408/5xx and transient errors.
response_retry = retry(
    retry=(
        retry_if_result(_is_retryable_response) | retry_if_exception(_is_retryable_exception)
    ),
    stop=stop_after_attempt(8),
    wait=_compute_retry_wait,
    reraise=True,
)


def create_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """Create a pre-configured httpx.AsyncClient with HTTP/2 support.

    The caller is responsible for using this within an async context manager
    or calling ``aclose()`` when done.
    """
    return httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        **kwargs,
    )
