"""Discover businesses with Yelp Fusion business search (YELP_API_KEY).

Yelp's API is paid after a short trial (free access ended in 2024), and its
terms limit how long Yelp data may be stored. Use it only if you have a plan
that allows your use case. Yelp gives no website field, only its own page URL.
"""
from __future__ import annotations

import os
from typing import Any

from ..http import client

SEARCH_URL = "https://api.yelp.com/v3/businesses/search"


def parse_businesses(data: dict[str, Any], category: str) -> list[dict[str, Any]]:
    out = []
    for b in data.get("businesses", []):
        if not b.get("name") or b.get("is_closed"):
            continue
        coords = b.get("coordinates") or {}
        out.append({
            "source": "yelp",
            "source_id": b.get("id"),
            "name": b["name"],
            "category": category,
            "address": ", ".join((b.get("location") or {}).get("display_address") or []) or None,
            "phone": b.get("phone") or b.get("display_phone") or None,
            "lat": coords.get("latitude"),
            "lon": coords.get("longitude"),
            "rating": b.get("rating"),
            "review_count": b.get("review_count"),
            "socials": {"yelp": b["url"].split("?")[0]} if b.get("url") else {},
        })
    return out


def discover(lat: float, lon: float, categories: list[str], radius_km: float, max_results: int = 100) -> list[dict[str, Any]]:
    key = os.environ.get("YELP_API_KEY")
    if not key:
        raise RuntimeError("YELP_API_KEY is not set (Yelp's API is paid after a trial)")
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    results: list[dict[str, Any]] = []
    with client() as c:
        for cat in categories:
            for offset in range(0, max_results, 50):
                params = {"latitude": lat, "longitude": lon, "radius": int(min(radius_km, 40) * 1000),
                          "term": cat.split("=")[-1].replace("_", " "), "limit": 50, "offset": offset}
                r = c.get(SEARCH_URL, params=params, headers=headers)
                r.raise_for_status()
                page = parse_businesses(r.json(), cat)
                results.extend(page)
                if len(r.json().get("businesses", [])) < 50:
                    break
    return results
