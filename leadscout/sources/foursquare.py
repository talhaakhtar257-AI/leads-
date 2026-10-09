"""Discover businesses with the Foursquare Places API (free monthly allowance; key in FOURSQUARE_API_KEY).

Create a *service key* in the Foursquare developer console. Some fields (for
example tel/website) may count as premium calls; check your plan's pricing.
"""
from __future__ import annotations

import os
from typing import Any

from ..http import client

SEARCH_URL = "https://places-api.foursquare.com/places/search"
API_VERSION = "2025-06-17"
FIELDS = "fsq_place_id,name,latitude,longitude,location,categories,tel,website,email,social_media"


def parse_results(data: dict[str, Any], category: str) -> list[dict[str, Any]]:
    out = []
    for p in data.get("results", []):
        name = p.get("name")
        if not name:
            continue
        loc = p.get("location") or {}
        main = ((p.get("geocodes") or {}).get("main") or {})  # older response shape
        social = p.get("social_media") or {}
        socials = {}
        if social.get("instagram"):
            socials["instagram"] = f"https://instagram.com/{social['instagram']}"
        if social.get("facebook_id"):
            socials["facebook"] = f"https://facebook.com/{social['facebook_id']}"
        out.append({
            "source": "foursquare",
            "source_id": p.get("fsq_place_id") or p.get("fsq_id"),
            "name": name,
            "category": category,
            "address": loc.get("formatted_address") or loc.get("address"),
            "phone": p.get("tel"),
            "website": p.get("website"),
            "email": p.get("email"),
            "lat": p.get("latitude", main.get("latitude")),
            "lon": p.get("longitude", main.get("longitude")),
            "socials": socials,
        })
    return out


def discover(lat: float, lon: float, categories: list[str], radius_km: float, limit: int = 50) -> list[dict[str, Any]]:
    key = os.environ.get("FOURSQUARE_API_KEY")
    if not key:
        raise RuntimeError("FOURSQUARE_API_KEY is not set (create a service key in the Foursquare developer console)")
    headers = {"Authorization": f"Bearer {key}", "X-Places-Api-Version": API_VERSION, "Accept": "application/json"}
    results: list[dict[str, Any]] = []
    with client() as c:
        for cat in categories:
            params = {"ll": f"{lat},{lon}", "radius": int(min(radius_km, 100) * 1000),
                      "query": cat.split("=")[-1].replace("_", " "), "limit": limit, "fields": FIELDS}
            r = c.get(SEARCH_URL, params=params, headers=headers)
            r.raise_for_status()
            results.extend(parse_results(r.json(), cat))
    return results
