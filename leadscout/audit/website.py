"""Website audit: turns a business's web presence into "fixable problem" signals."""
from __future__ import annotations

import re
import time
from datetime import date
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..db import domain_of
from ..enrich.contacts import best_email, extract_contacts
from ..http import client
from . import pagespeed
from .newness import newness_evidence

SOCIAL_HOSTS = ("facebook.com", "instagram.com", "fb.com", "linktr.ee", "tiktok.com")
FREE_SUBDOMAINS = ("wixsite.com", "blogspot.com", "wordpress.com", "weebly.com", "business.site",
                   "godaddysites.com", "square.site", "webnode.page", "jimdosite.com", "carrd.co")
BOOKING_HINTS = ("book now", "book online", "booking", "appointment", "reserve", "reservation", "order online",
                 "order now", "schedule", "calendly", "opentable", "fresha", "setmore", "acuity", "foodpanda",
                 "ubereats", "deliveroo", "talabat", "zomato", "doordash", "add to cart")
COPYRIGHT_RE = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", re.I)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    return url


def analyze_html(html: str, final_url: str, today: date | None = None) -> tuple[list[str], dict[str, Any]]:
    """Pure HTML checks (unit-testable). Returns (signals, details)."""
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    signals: list[str] = []
    details: dict[str, Any] = {}

    if final_url.lower().startswith("http://"):
        signals.append("no_https")

    if not soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}):
        signals.append("not_mobile_friendly")

    years = [int(y) for y in COPYRIGHT_RE.findall(html)]
    if years:
        details["copyright_year"] = max(years)
        if max(years) < today.year - 2:
            signals.append("outdated_copyright")

    if not soup.find("form"):
        details["no_form_on_homepage"] = True

    low = soup.get_text(" ").lower() + " " + " ".join(a.get("href", "").lower() for a in soup.find_all("a"))
    if not any(h in low for h in BOOKING_HINTS):
        signals.append("no_booking")

    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    details["title"] = title[:120]
    if not title or not desc or not (desc.get("content") or "").strip():
        signals.append("missing_seo_basics")
    return signals, details


def audit_business(biz: dict[str, Any], use_pagespeed: bool = False) -> dict[str, Any]:
    """Fetch the business website (+ contact pages) and return signals, contacts and details."""
    signals: list[str] = []
    details: dict[str, Any] = {}
    contacts = {"emails": [biz["email"]] if biz.get("email") else [], "phones": [], "socials": dict(biz.get("socials") or {})}

    evidence = newness_evidence(biz)
    if evidence:
        signals.append("new_business")
        details["new_business"] = evidence

    # Reputation signals (only available from Google Places / Yelp).
    if biz.get("rating") is not None and biz["rating"] < 4.0:
        signals.append("low_rating")
    if biz.get("review_count") is not None and biz["review_count"] < 20:
        signals.append("few_reviews")

    website = biz.get("website")
    domain = domain_of(website)
    if not website:
        signals.append("no_website")
    elif any(h in (domain or "") for h in SOCIAL_HOSTS):
        signals.append("social_only")
        platform = next((h.split(".")[0] for h in SOCIAL_HOSTS if h in (domain or "")), "social")
        contacts["socials"].setdefault("facebook" if platform == "fb" else platform, website)
    else:
        if any((domain or "").endswith(s) for s in FREE_SUBDOMAINS):
            signals.append("free_subdomain")
        url = normalize_url(website)
        try:
            with client(timeout=15, browser=True) as c:
                t0 = time.monotonic()
                r = c.get(url)
                details["load_seconds"] = round(time.monotonic() - t0, 2)
                details["status_code"] = r.status_code
                details["final_url"] = str(r.url)
                if r.status_code >= 400:
                    signals.append("site_down")
                else:
                    html = r.text
                    s, d = analyze_html(html, str(r.url))
                    signals += s
                    details.update(d)
                    found = extract_contacts(html, str(r.url))
                    pages_with_forms = 0 if d.get("no_form_on_homepage") else 1
                    for link in found["contact_links"]:
                        try:
                            sub = c.get(link)
                            if sub.status_code < 400:
                                more = extract_contacts(sub.text)
                                found["emails"] = sorted(set(found["emails"]) | set(more["emails"]))
                                found["phones"] = sorted(set(found["phones"]) | set(more["phones"]))
                                for k, v in more["socials"].items():
                                    found["socials"].setdefault(k, v)
                                if "<form" in sub.text.lower():
                                    pages_with_forms += 1
                        except httpx.HTTPError:
                            pass
                    if pages_with_forms == 0:
                        signals.append("no_contact_form")
                    contacts["emails"] = sorted(set(contacts["emails"]) | set(found["emails"]))
                    contacts["phones"] = found["phones"]
                    for k, v in found["socials"].items():
                        contacts["socials"].setdefault(k, v)
                    if not found["socials"] and not biz.get("socials"):
                        signals.append("no_social_links")
                    if details["load_seconds"] > 4:
                        signals.append("slow_site")
        except httpx.HTTPError as e:
            signals.append("site_down")
            details["error"] = type(e).__name__

        if use_pagespeed and "site_down" not in signals:
            score = pagespeed.mobile_performance(normalize_url(website))
            if score is not None:
                details["pagespeed_mobile"] = score
                if score < 50 and "slow_site" not in signals:
                    signals.append("slow_site")

    email = best_email(contacts["emails"], domain)
    if not email and "no_website" not in signals:
        signals.append("no_email_found")

    return {
        "signals": list(dict.fromkeys(signals)),
        "details": details,
        "email": email,
        "phone": biz.get("phone") or (contacts["phones"][0] if contacts["phones"] else None),
        "socials": contacts["socials"],
        "all_emails": contacts["emails"],
    }
