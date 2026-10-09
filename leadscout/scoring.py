"""Deterministic lead scoring: how badly does this business need *your* service, and can you reach them?"""
from __future__ import annotations

from typing import Any

# Service -> {signal: weight}. Signals not listed don't count for that service.
SERVICE_PROFILES: dict[str, dict[str, int]] = {
    "web_design": {
        "no_website": 45, "social_only": 40, "site_down": 40, "free_subdomain": 30, "not_mobile_friendly": 30,
        "outdated_copyright": 20, "no_https": 15, "slow_site": 15, "no_contact_form": 10, "missing_seo_basics": 5,
    },
    "seo": {
        "missing_seo_basics": 30, "slow_site": 20, "not_mobile_friendly": 20, "no_https": 15, "few_reviews": 15,
        "social_only": 25, "no_website": 20, "free_subdomain": 15, "low_rating": 10,
    },
    "booking_system": {
        "no_booking": 45, "no_contact_form": 15, "no_website": 20, "social_only": 15, "not_mobile_friendly": 10,
    },
    "social_media": {
        "no_social_links": 40, "few_reviews": 20, "no_website": 10, "outdated_copyright": 10, "low_rating": 10,
    },
    "reputation": {"low_rating": 50, "few_reviews": 40, "no_social_links": 10},
    "maintenance": {
        "site_down": 45, "no_https": 30, "slow_site": 25, "outdated_copyright": 20, "not_mobile_friendly": 15,
    },
    "general_marketing": {
        "no_website": 30, "social_only": 25, "not_mobile_friendly": 15, "missing_seo_basics": 15, "no_booking": 10,
        "no_social_links": 15, "few_reviews": 15, "low_rating": 15, "outdated_copyright": 10, "no_https": 10,
    },
}


def score_lead(biz: dict[str, Any], service: str) -> int:
    weights = SERVICE_PROFILES.get(service, SERVICE_PROFILES["general_marketing"])
    need = min(85, sum(weights.get(s, 0) for s in biz.get("signals") or []))
    has_email = bool(biz.get("email"))
    has_phone = bool(biz.get("phone"))
    reach = (10 if has_email else 0) + (5 if has_phone else 0)
    score = need + reach
    if not has_email and not has_phone:
        score = min(score, 20)  # can't contact them, so it's not a real lead
    return int(max(0, min(100, score)))


def relevant_signals(signals: list[str], service: str, top: int = 3) -> list[str]:
    """Signals ordered by how strongly they support pitching this service."""
    weights = SERVICE_PROFILES.get(service, SERVICE_PROFILES["general_marketing"])
    ranked = sorted((s for s in signals if weights.get(s)), key=lambda s: -weights[s])
    return ranked[:top]
