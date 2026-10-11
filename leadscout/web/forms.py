"""Campaign form <-> campaign.yaml, for the setup wizard and the Settings page."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..config import Campaign
from ..sources.overpass import CATEGORY_TAGS

SERVICES: dict[str, tuple[str, str]] = {
    "web_design": ("Websites", "Businesses with no website, a broken or old one, or one that fails on phones."),
    "seo": ("Google ranking (SEO)", "Sites Google shows poorly: missing titles, slow, not mobile-friendly."),
    "booking_system": ("Online booking / ordering", "Restaurants, salons and clinics with no way to book or order online."),
    "social_media": ("Social media", "Businesses with no social links and few reviews."),
    "reputation": ("Reviews & reputation", "Low Google ratings or very few reviews."),
    "maintenance": ("Website care & fixes", "Sites that are down, slow or not secure."),
    "general_marketing": ("General marketing", "A bit of everything: any visible online weakness."),
}

CATEGORY_LABELS: dict[str, str] = {
    "restaurant": "Restaurants", "cafe": "Cafés", "fast_food": "Fast food", "bakery": "Bakeries",
    "dentist": "Dentists", "clinic": "Clinics", "doctor": "Doctors", "pharmacy": "Pharmacies",
    "salon": "Hair salons", "beauty": "Beauty parlours", "gym": "Gyms", "hotel": "Hotels & guest houses",
    "car_repair": "Car repair", "real_estate": "Real estate agents", "lawyer": "Lawyers",
    "accountant": "Accountants", "school": "Schools & colleges", "tutor": "Tuition centres", "vet": "Vets",
    "florist": "Florists", "clothes": "Clothing shops", "electronics": "Electronics shops",
    "furniture": "Furniture shops", "optician": "Opticians", "travel_agency": "Travel agents",
}
assert set(CATEGORY_LABELS) == set(CATEGORY_TAGS)

SOURCES: dict[str, tuple[str, str]] = {
    "overpass": ("OpenStreetMap", "free"),
    "foursquare": ("Foursquare", "free-tier"),
    "google_places": ("Google Places", "free-tier"),
    "yelp": ("Yelp", "paid"),
}
LANGUAGES = ["English", "Urdu", "Roman Urdu"]
PLACEHOLDER_SENDER = "Your Name"

HEADER = ("# LeadScout campaign. Edit it in the dashboard (Settings), or by hand.\n"
          "# Full list of options: see campaigns/example.yaml\n")


def needs_setup(c: Campaign | None) -> bool:
    return c is None or c.sender.name.strip() in ("", PLACEHOLDER_SENDER)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "campaign"


def form_to_data(form, existing: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Build campaign data from a submitted form, keeping existing values for fields the form doesn't show.

    Returns (data, problems) where problems are readable messages for values that couldn't be read.
    """
    data: dict[str, Any] = dict(existing or {})
    problems: list[str] = []
    get = lambda k, d="": (form.get(k) or d).strip()  # noqa: E731

    def number(key: str, default, cast, label: str):
        raw = get(key, str(default)) or str(default)
        try:
            return cast(float(raw)) if cast is int and float(raw).is_integer() else cast(raw)
        except ValueError:
            problems.append(f"{label}: '{raw}' is not a number.")
            return default

    categories = [c for c in form.getlist("categories") if c in CATEGORY_TAGS]
    for extra in (" ".join(x.split()) for x in re.split(r"[,،\n]", get("extra_categories"))):
        if not extra or extra in categories:
            continue
        if "=" in extra or re.fullmatch(r"[\w ]+", extra):
            categories.append(extra)
        else:
            problems.append(f"Business type '{extra}': use only letters, numbers and spaces.")
    language = get("language", "English")
    if language == "other":
        language = get("language_other") or "English"
    location = get("location")
    service = get("service", "web_design")
    if service == "custom":
        service = " ".join(get("service_custom").split())[:60]
        if not service:
            problems.append("What you sell: type it in the 'Something else' box, e.g. logo design.")
            service = "general_marketing"

    def coordinate(key: str, low: float, high: float) -> float | None:
        raw = get(key)
        if not raw:
            return None
        try:
            value = round(float(raw), 6)
        except ValueError:
            return None
        return value if low <= value <= high else None

    center_lat, center_lon = coordinate("center_lat", -90, 90), coordinate("center_lon", -180, 180)
    if center_lat is None or center_lon is None:
        center_lat = center_lon = None

    data.update({
        "name": get("name") or data.get("name") or f"{_slug(location.split(',')[0])}-{_slug(service)}",
        "location": location,
        "country_code": re.sub(r"\D", "", get("country_code")),
        "radius_km": number("radius_km", 5, float, "Distance"),
        "center_lat": center_lat,
        "center_lon": center_lon,
        "categories": categories,
        "service": service,
        "service_pitch": get("service_pitch") or Campaign.model_fields["service_pitch"].default,
        "language": language,
        "tone": get("tone", "friendly"),
    })
    sender = dict(data.get("sender") or {})
    for k in ("name", "company", "email", "phone", "website", "address"):
        sender[k] = get(f"sender_{k}")
    data["sender"] = sender

    if form.get("advanced"):
        data["sources"] = [s for s in form.getlist("sources") if s in SOURCES] or ["overpass"]
        data["llm"] = get("llm", "auto")
        data["min_score"] = number("min_score", 40, int, "Minimum score")
        data["auto_send"] = bool(form.get("auto_send"))
        data["pagespeed"] = bool(form.get("pagespeed"))
        limits = dict(data.get("limits") or {})
        limits["daily_emails"] = number("daily_emails", 30, int, "Emails per day")
        days = [int(d) for d in re.findall(r"\d+", get("followup_days", "3, 7"))]
        limits["followup_days"] = days or [3, 7]
        data["limits"] = limits
    return data, problems


def friendly_errors(e: ValidationError) -> list[str]:
    names = {"location": "Location", "categories": "Business types", "sender": "Your details",
             "radius_km": "Distance", "sources": "Sources", "name": "Campaign name"}
    out = []
    for err in e.errors():
        field = ".".join(str(p) for p in err["loc"])
        label = names.get(str(err["loc"][0]), field) if err["loc"] else "Settings"
        msg = err["msg"]
        if err["type"] in ("too_short", "missing") and str(err["loc"][0]) == "categories":
            msg = "pick at least one"
        out.append(f"{label}: {msg}")
    return out


def validate(data: dict[str, Any]) -> tuple[Campaign | None, list[str]]:
    errors = []
    if not data.get("location") and data.get("center_lat") is None:
        errors.append("Area: type where to search, e.g. 'Gulberg, Lahore, Pakistan', or click the map.")
    if not data.get("categories"):
        errors.append("Business types: pick at least one.")
    sender = data.get("sender") or {}
    if not sender.get("name"):
        errors.append("Your name: needed to sign your messages.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", sender.get("email") or ""):
        errors.append("Email: needed as the sender address of your messages.")
    if not (sender.get("address") or "").strip():
        errors.append("Postal address: anti-spam laws require it in sales emails.")
    if errors:
        return None, errors
    try:
        return Campaign.model_validate(data), []
    except ValidationError as e:
        return None, friendly_errors(e)


def save_campaign(path: Path, data: dict[str, Any]) -> None:
    data = {k: v for k, v in data.items() if not (k in ("center_lat", "center_lon") and v is None)}
    text = HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def load_raw(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    except yaml.YAMLError:
        data = None
    return data if isinstance(data, dict) else {}
