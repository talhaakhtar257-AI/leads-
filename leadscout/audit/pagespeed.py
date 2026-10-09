"""Google PageSpeed Insights (free; set PAGESPEED_API_KEY for a usable quota)."""
from __future__ import annotations

import os

import httpx

from ..http import client

API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def mobile_performance(url: str) -> int | None:
    params = {"url": url, "strategy": "mobile", "category": "performance"}
    if os.environ.get("PAGESPEED_API_KEY"):
        params["key"] = os.environ["PAGESPEED_API_KEY"]
    try:
        with client(timeout=90) as c:
            r = c.get(API, params=params)
            r.raise_for_status()
            score = r.json()["lighthouseResult"]["categories"]["performance"]["score"]
            return round(score * 100) if score is not None else None
    except (httpx.HTTPError, KeyError, ValueError):
        return None
