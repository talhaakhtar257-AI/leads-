"""Discover businesses from OpenStreetMap (free, no API key).

Geocoding uses Nominatim; business search uses the Overpass API.
Both are free community services: keep request volume modest.
"""
from __future__ import annotations

import re
import threading
import time
from functools import lru_cache
from typing import Any

import httpx

from ..http import client, request_with_retry

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Public mirrors, tried in order when the main server is busy or down.
OVERPASS_URLS = [
    OVERPASS_URL,
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Nominatim's usage policy: at most one request per second.
_nominatim_lock = threading.Lock()
_nominatim_last = 0.0

# Friendly category name -> OSM tag filters.
CATEGORY_TAGS: dict[str, list[str]] = {
    "restaurant": ['"amenity"="restaurant"'],
    "cafe": ['"amenity"="cafe"'],
    "fast_food": ['"amenity"="fast_food"'],
    "bakery": ['"shop"="bakery"'],
    "dentist": ['"amenity"="dentist"', '"healthcare"="dentist"'],
    "clinic": ['"amenity"="clinic"', '"healthcare"="clinic"'],
    "doctor": ['"amenity"="doctors"', '"healthcare"="doctor"'],
    "pharmacy": ['"amenity"="pharmacy"'],
    "salon": ['"shop"="hairdresser"'],
    "beauty": ['"shop"="beauty"'],
    "gym": ['"leisure"="fitness_centre"'],
    "hotel": ['"tourism"="hotel"', '"tourism"="guest_house"'],
    "car_repair": ['"shop"="car_repair"'],
    "real_estate": ['"office"="estate_agent"'],
    "lawyer": ['"office"="lawyer"'],
    "accountant": ['"office"="accountant"'],
    "school": ['"amenity"="school"', '"amenity"="college"'],
    "tutor": ['"amenity"="prep_school"'],
    "vet": ['"amenity"="veterinary"'],
    "florist": ['"shop"="florist"'],
    "clothes": ['"shop"="clothes"'],
    "electronics": ['"shop"="electronics"'],
    "furniture": ['"shop"="furniture"'],
    "optician": ['"shop"="optician"'],
    "travel_agency": ['"shop"="travel_agency"'],
}


def tag_filters(category: str) -> list[str]:
    """Known category, or a raw OSM tag such as 'shop=tailor'."""
    if category in CATEGORY_TAGS:
        return CATEGORY_TAGS[category]
    if "=" in category:
        k, v = (x.strip() for x in category.split("=", 1))
        if not re.fullmatch(r"[\w:.-]+", k) or not re.fullmatch(r"[\w:. -]+", v):
            raise ValueError(f"The custom business type {category!r} isn't valid. Use key=value, e.g. shop=tailor.")
        return [f'"{k}"="{v}"']
    raise ValueError(f"Unknown category {category!r}. Use one of {sorted(CATEGORY_TAGS)} or a raw OSM tag like shop=tailor")


@lru_cache(maxsize=64)
def geocode(location: str) -> tuple[float, float]:
    global _nominatim_last
    with _nominatim_lock:
        wait = 1.1 - (time.monotonic() - _nominatim_last)
        if wait > 0:
            time.sleep(wait)
        try:
            with client() as c:
                r = request_with_retry(c, "GET", NOMINATIM_URL, params={"q": location, "format": "json", "limit": 1})
        finally:
            _nominatim_last = time.monotonic()
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"Could not find the location {location!r}. Try adding the city and country.")
    return float(data[0]["lat"]), float(data[0]["lon"])


def run_query(c: httpx.Client, query: str) -> dict[str, Any]:
    """Run an Overpass query, falling back to mirrors when a server is overloaded or unreachable."""
    last: Exception | None = None
    for i, url in enumerate(OVERPASS_URLS):
        try:
            r = request_with_retry(c, "POST", url, data={"data": query}, attempts=2 if i == 0 else 1)
            if r.status_code == 400:  # our query is wrong (e.g. a typo in a custom tag); mirrors won't help
                raise ValueError("OpenStreetMap could not understand the search. Check the custom business "
                                 "types under 'Other kinds' (format: key=value, e.g. shop=tailor).")
            r.raise_for_status()
            return r.json()
        except ValueError:
            raise
        except httpx.HTTPError as e:
            last = e
    raise RuntimeError(f"OpenStreetMap search is busy or unreachable right now ({last}). Try again in a few minutes.")


def build_query(category: str, lat: float, lon: float, radius_m: int) -> str:
    parts = "".join(f"nwr[{f}][\"name\"](around:{radius_m},{lat},{lon});" for f in tag_filters(category))
    return f"[out:json][timeout:90];({parts});out center tags meta;"


def _first(tags: dict[str, str], *keys: str) -> str | None:
    for k in keys:
        if tags.get(k):
            return tags[k].split(";")[0].strip()
    return None


def parse_elements(data: dict[str, Any], category: str) -> list[dict[str, Any]]:
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
        address = ", ".join(x for x in (street, tags.get("addr:suburb"), tags.get("addr:city")) if x) or None
        socials = {
            k: v for k, v in {
                "facebook": _first(tags, "contact:facebook", "facebook"),
                "instagram": _first(tags, "contact:instagram", "instagram"),
                "whatsapp": _first(tags, "contact:whatsapp", "whatsapp"),
            }.items() if v
        }
        out.append({
            "source": "osm",
            "source_id": f"{el.get('type')}/{el.get('id')}",
            "name": name,
            "category": category,
            "address": address,
            "phone": _first(tags, "phone", "contact:phone", "contact:mobile", "mobile"),
            "website": _first(tags, "website", "contact:website", "url"),
            "email": _first(tags, "email", "contact:email"),
            "lat": lat,
            "lon": lon,
            "opening_hours": tags.get("opening_hours"),
            "socials": socials,
            "meta": {k: v for k, v in {
                "osm_version": el.get("version"),
                "osm_timestamp": el.get("timestamp"),
                "start_date": tags.get("start_date"),
                "opening_date": tags.get("opening_date"),
            }.items() if v is not None},
        })
    return out


def discover(location: str, categories: list[str], radius_km: float,
             center: tuple[float, float] | None = None) -> list[dict[str, Any]]:
    lat, lon = center or geocode(location)
    results: list[dict[str, Any]] = []
    with client(timeout=100) as c:
        for cat in categories:
            data = run_query(c, build_query(cat, lat, lon, int(radius_km * 1000)))
            results.extend(parse_elements(data, cat))
    return results
