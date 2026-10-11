"""Shared HTTP client settings."""
from __future__ import annotations

import httpx

USER_AGENT = "LeadScout/0.1 (+https://github.com/talhaakhtar257-ai/leads-)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 LeadScout/0.1"
)


def client(timeout: float = 20, browser: bool = False) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": BROWSER_UA if browser else USER_AGENT},
    )


RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER = 60.0


def _sleep(seconds: float) -> None:  # patched in tests
    import time
    time.sleep(seconds)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after", "")
    try:
        return min(float(value), MAX_RETRY_AFTER)
    except ValueError:
        return None


def request_with_retry(c: httpx.Client, method: str, url: str, *, attempts: int = 4, base_delay: float = 2.0,
                       **kwargs) -> httpx.Response:
    """Send a request, retrying rate limits (429), server errors (5xx) and network hiccups with backoff.

    Honours Retry-After. Returns the last response (callers still call raise_for_status) or re-raises
    the last network error.
    """
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = c.request(method, url, **kwargs)
        except httpx.TransportError as e:  # timeouts, connection resets, DNS failures
            last_error = e
            response = None
        if response is not None and response.status_code not in RETRY_STATUS:
            return response
        if attempt == attempts - 1:
            break
        wait = (_retry_after(response) if response is not None else None) or base_delay * (2 ** attempt)
        _sleep(wait)
    if response is not None:
        return response
    assert last_error is not None
    raise last_error
