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
