"""Safety for a dashboard that runs on the user's own computer.

* Host check: only answer to localhost names (blocks DNS-rebinding pages).
* Cross-site check: refuse state-changing requests that come from another website,
  so a page you visit can't tell LeadScout to send emails or change settings.
* safe_url: scraped links can be "javascript:..."; only let real links into href.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "testserver"}


def _host(value: str | None) -> str | None:
    if not value:
        return None
    netloc = urlsplit(value if "//" in value else f"//{value}").netloc.lower()
    return netloc or None


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts: set[str] | None = None):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts  # None = any host (user chose to expose it on their network)

    async def dispatch(self, request: Request, call_next):
        host_header = request.headers.get("host", "")
        hostname = re.sub(r":\d+$", "", host_header).lower()
        if self.allowed_hosts is not None and hostname not in self.allowed_hosts:
            return PlainTextResponse("LeadScout only answers on localhost.", status_code=400)
        if request.method not in SAFE_METHODS:
            source = request.headers.get("origin") or request.headers.get("referer")
            # Browsers always send Origin on cross-site POSTs. No Origin/Referer means a non-browser client.
            if source and source != "null" and _host(source) != host_header.lower():
                return PlainTextResponse("Blocked: this request came from another website.", status_code=403)
            if source == "null":
                return PlainTextResponse("Blocked: request from an opaque origin.", status_code=403)
        return await call_next(request)


def safe_url(url: str | None) -> str:
    """Return a link that is safe in href, or '#'. Bare domains get http://."""
    if not url:
        return "#"
    u = str(url).strip()
    scheme = urlsplit(u).scheme.lower()
    if scheme in ("http", "https", "mailto", "tel"):
        return u
    if not scheme and re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", u, re.I):
        return "http://" + u
    return "#"


def same_site_path(referer: str | None, fallback: str = "/") -> str:
    """Path+query of our own referer, for post-redirect-get without an open redirect."""
    if not referer:
        return fallback
    parts = urlsplit(referer)
    path = parts.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        return fallback
    return path + (f"?{parts.query}" if parts.query else "")
