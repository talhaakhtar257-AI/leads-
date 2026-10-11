"""Spot recently opened businesses: new owners still need a website, a Google profile and reviews."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

START_DATE_MONTHS = 12   # an explicit opening date within this window
NEW_MAP_ENTRY_MONTHS = 6  # first added to OpenStreetMap within this window


def _months_ago(d: date, today: date) -> float:
    return (today - d).days / 30.44


def _parse_date(value: str | None) -> date | None:
    """OSM dates may be 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD' (or ISO timestamps)."""
    if not value:
        return None
    m = re.match(r"^\s*(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(value))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1))
    except ValueError:
        return None


def newness_evidence(biz: dict[str, Any], today: date | None = None) -> str | None:
    """Return a short reason if the business looks recently opened, else None."""
    today = today or date.today()
    meta = biz.get("meta") or {}

    opened = _parse_date(meta.get("start_date") or meta.get("opening_date"))
    if opened and opened <= today and _months_ago(opened, today) <= START_DATE_MONTHS:
        return f"opened {opened.isoformat()}"

    version, ts = meta.get("osm_version"), meta.get("osm_timestamp")
    if version is not None and int(version) <= 2 and ts:
        try:
            added = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date()
        except ValueError:
            added = None
        if added and _months_ago(added, today) <= NEW_MAP_ENTRY_MONTHS:
            return f"added to OpenStreetMap {added.isoformat()}"
    # A low review count alone is not evidence: plenty of old shops have few reviews
    # (that is the separate "few_reviews" signal), and congratulating them on opening is wrong.
    return None


def is_new(biz: dict[str, Any], today: date | None = None) -> bool:
    return newness_evidence(biz, today) is not None
