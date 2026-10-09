"""Cheap email validation: syntax + MX record lookup (no SMTP probing)."""
from __future__ import annotations

from functools import lru_cache

import dns.exception
import dns.resolver

from .contacts import EMAIL_RE


@lru_cache(maxsize=2048)
def has_mx(domain: str) -> bool:
    try:
        return len(dns.resolver.resolve(domain, "MX", lifetime=5)) > 0
    except (dns.exception.DNSException, OSError):
        return False


def verify(email: str) -> bool:
    if not email or not EMAIL_RE.fullmatch(email):
        return False
    return has_mx(email.rsplit("@", 1)[1])
