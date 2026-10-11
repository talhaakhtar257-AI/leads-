"""Export leads to CSV (opens in Excel / Google Sheets)."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from ..config import Campaign
from ..db import DB
from ..outreach.whatsapp import wa_link
from ..signals import SIGNALS

COLUMNS = ["id", "name", "category", "score", "status", "reason", "problems", "email", "phone", "whatsapp_link",
           "website", "address", "rating", "review_count", "facebook", "instagram", "lat", "lon"]


def csv_safe(value: Any) -> Any:
    """Stop spreadsheet apps from running scraped text as a formula (=HYPERLINK(...), @SUM(...), ...).

    Phone numbers like "+92 300 1234567" and negative numbers are left alone.
    """
    if not isinstance(value, str) or not value:
        return value
    if value[0] in "=@\t\r" or (value[0] in "+-" and not re.fullmatch(r"[+\-][\d\s().\-]*", value)):
        return "'" + value
    return value


def safe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: csv_safe(v) for k, v in r.items()} for r in rows]


def lead_rows(db: DB, campaign: Campaign) -> list[dict[str, Any]]:
    rows = []
    for b in db.businesses(campaign.name):
        wa_msg = db.messages("m.business_id = ? AND m.channel = 'whatsapp' AND m.step = 0", (b["id"],))
        text = wa_msg[0]["body"] if wa_msg else f"Hi {b['name']}!"
        rows.append({
            "id": b["id"],
            "name": b["name"],
            "category": b["category"],
            "score": b["score"],
            "status": b["status"],
            "reason": b["reason"],
            "problems": "; ".join(SIGNALS[s].title if s in SIGNALS else s for s in b["signals"]),
            "email": b["email"],
            "phone": b["phone"],
            "whatsapp_link": wa_link(b["phone"], text, campaign.country_code),
            "website": b["website"],
            "address": b["address"],
            "rating": b["rating"],
            "review_count": b["review_count"],
            "facebook": b["socials"].get("facebook"),
            "instagram": b["socials"].get("instagram"),
            "lat": b["lat"],
            "lon": b["lon"],
        })
    return rows


def export_csv(db: DB, campaign: Campaign, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(safe_rows(lead_rows(db, campaign)))
    return path
