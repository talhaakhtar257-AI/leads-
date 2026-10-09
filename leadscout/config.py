"""Campaign configuration (campaign.yaml) and environment loading (.env)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

SourceName = Literal["overpass", "google_places", "foursquare", "yelp"]


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Sender(BaseModel):
    name: str = "Your Name"
    company: str = "Your Agency"
    email: str = "you@example.com"
    phone: str = ""
    website: str = ""
    # Physical postal address: required in commercial email by CAN-SPAM.
    address: str = "Your street address, City, Country"


class Limits(BaseModel):
    daily_emails: int = 30
    min_delay_seconds: int = 45
    max_delay_seconds: int = 120
    followup_days: list[int] = Field(default_factory=lambda: [3, 7])


class Campaign(BaseModel):
    name: str
    location: str  # free-text place name, geocoded via OpenStreetMap Nominatim
    country_code: str = ""  # phone country code without "+", e.g. "92" or "1"
    radius_km: float = 5
    categories: list[str]
    service: str = "web_design"  # key in scoring.SERVICE_PROFILES
    service_pitch: str = "I build fast, mobile-friendly websites for local businesses."
    language: str = "English"
    # Discovery sources, merged and de-duplicated. overpass is free; the others need API keys.
    sources: list[SourceName] = Field(default_factory=lambda: ["overpass"], min_length=1)
    min_score: int = 40  # leads below this are not drafted
    llm: str = "auto"  # auto | gemini | groq | ollama | claude | template
    auto_send: bool = False
    pagespeed: bool = False  # needs PAGESPEED_API_KEY for useful quota
    sender: Sender = Field(default_factory=Sender)
    limits: Limits = Field(default_factory=Limits)

    @model_validator(mode="before")
    @classmethod
    def _single_source_compat(cls, data):
        """Older campaign files used `source: overpass`; treat it as `sources: [overpass]`."""
        if isinstance(data, dict) and "source" in data:
            data = dict(data)
            single = data.pop("source")
            data.setdefault("sources", [single])
        return data


def load_campaign(path: str | Path) -> Campaign:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Campaign.model_validate(data)
