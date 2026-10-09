"""Discover businesses with Google Places API (New) Text Search.

Needs GOOGLE_PLACES_API_KEY. Google gives a free monthly usage quota;
check current pricing in the Google Cloud console before large runs.
Adds rating and review count, which power the reputation signals.
"""
from __future__ import annotations

import os
from typing import Any

from ..http import client

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.internationalPhoneNumber",
    "places.nationalPhoneNumber", "places.websiteUri", "places.location", "places.rating",
    "places.userRatingCount", "places.businessStatus", "nextPageToken",
])


def parse_places(data: dict[str, Any], category: str) -> list[dict[str, Any]]:
    out = []
    for p in data.get("places", []):
        if p.get("businessStatus") not in (None, "OPERATIONAL"):
            continue
        out.append({
            "source": "google_places",
            "source_id": p.get("id"),
            "name": (p.get("displayName") or {}).get("text", ""),
            "category": category,
            "address": p.get("formattedAddress"),
            "phone": p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"),
            "website": p.get("websiteUri"),
            "lat": (p.get("location") or {}).get("latitude"),
            "lon": (p.get("location") or {}).get("longitude"),
            "rating": p.get("rating"),
            "review_count": p.get("userRatingCount"),
        })
    return [b for b in out if b["name"]]


def discover(location: str, categories: list[str], max_pages: int = 3) -> list[dict[str, Any]]:
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set (or use source: overpass, which is free)")
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK}
    results: list[dict[str, Any]] = []
    with client() as c:
        for cat in categories:
            body: dict[str, Any] = {"textQuery": f"{cat.replace('_', ' ')} in {location}", "pageSize": 20}
            for _ in range(max_pages):
                r = c.post(SEARCH_URL, json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
                results.extend(parse_places(data, cat))
                token = data.get("nextPageToken")
                if not token:
                    break
                body["pageToken"] = token
    return results
