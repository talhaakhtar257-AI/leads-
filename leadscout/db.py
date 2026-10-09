"""SQLite storage: businesses (leads), outreach messages and the suppression list."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign TEXT NOT NULL,
    source TEXT,
    source_id TEXT,
    name TEXT NOT NULL,
    category TEXT,
    address TEXT,
    phone TEXT,
    website TEXT,
    domain TEXT,
    email TEXT,
    lat REAL,
    lon REAL,
    rating REAL,
    review_count INTEGER,
    opening_hours TEXT,
    socials TEXT DEFAULT '{}',
    signals TEXT DEFAULT '[]',
    audit TEXT DEFAULT '{}',
    score INTEGER,
    reason TEXT,
    status TEXT DEFAULT 'new',   -- new | audited | drafted | contacted | replied | won | lost | unsubscribed
    phone_key TEXT,
    name_key TEXT,
    created_at TEXT,
    audited_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_biz_phone ON businesses(phone_key);
CREATE INDEX IF NOT EXISTS idx_biz_domain ON businesses(domain);
CREATE INDEX IF NOT EXISTS idx_biz_name ON businesses(name_key);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    channel TEXT NOT NULL,        -- email | whatsapp
    step INTEGER DEFAULT 0,       -- 0 = first touch, 1.. = follow-ups
    subject TEXT,
    body TEXT,
    status TEXT DEFAULT 'draft',  -- draft | approved | scheduled | sent | skipped | cancelled
    scheduled_at TEXT,
    sent_at TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS suppression (
    value TEXT PRIMARY KEY,       -- lower-cased email, domain or phone digits
    reason TEXT,
    created_at TEXT
);
"""

JSON_FIELDS = ("socials", "signals", "audit")

# Many businesses share these hosts, so a matching domain doesn't mean the same business.
SHARED_HOSTS = ("facebook.com", "fb.com", "instagram.com", "linktr.ee", "tiktok.com", "google.com",
                "goo.gl", "wa.me", "whatsapp.com", "youtube.com", "twitter.com", "x.com", "linkedin.com")


def dedupe_domain(url: str | None) -> str | None:
    d = domain_of(url)
    if not d or any(d == h or d.endswith("." + h) for h in SHARED_HOSTS):
        return None
    return d


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def phone_key(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-9:] if len(digits) >= 7 else None


def name_key(name: str, address: str | None) -> str:
    raw = f"{name} {address or ''}".lower()
    return re.sub(r"[^a-z0-9]+", "", raw)


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    m = re.match(r"^(?:[a-z]+://)?(?:www\.)?([^/:?#]+)", url.strip().lower())
    return m.group(1) if m else None


class DB:
    def __init__(self, path: str | Path = "leads.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---------- businesses ----------
    def find_duplicate(self, biz: dict[str, Any]) -> int | None:
        """Dedupe across *all* campaigns by phone, website domain, or name+address."""
        checks = [
            ("phone_key", phone_key(biz.get("phone"))),
            ("domain", dedupe_domain(biz.get("website"))),
            ("name_key", name_key(biz["name"], biz.get("address"))),
        ]
        for col, val in checks:
            if not val:
                continue
            row = self.conn.execute(f"SELECT id FROM businesses WHERE {col} = ?", (val,)).fetchone()
            if row:
                return row["id"]
        return None

    def insert_business(self, campaign: str, biz: dict[str, Any]) -> int | None:
        """Insert a new business; returns None if it is a duplicate."""
        if self.find_duplicate(biz):
            return None
        row = {
            "campaign": campaign,
            "source": biz.get("source"),
            "source_id": biz.get("source_id"),
            "name": biz["name"],
            "category": biz.get("category"),
            "address": biz.get("address"),
            "phone": biz.get("phone"),
            "website": biz.get("website"),
            "domain": dedupe_domain(biz.get("website")),
            "email": biz.get("email"),
            "lat": biz.get("lat"),
            "lon": biz.get("lon"),
            "rating": biz.get("rating"),
            "review_count": biz.get("review_count"),
            "opening_hours": biz.get("opening_hours"),
            "socials": json.dumps(biz.get("socials") or {}),
            "phone_key": phone_key(biz.get("phone")),
            "name_key": name_key(biz["name"], biz.get("address")),
            "created_at": now(),
        }
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cur = self.conn.execute(f"INSERT INTO businesses ({cols}) VALUES ({marks})", tuple(row.values()))
        self.conn.commit()
        return cur.lastrowid

    def update_business(self, biz_id: int, **fields: Any) -> None:
        for f in JSON_FIELDS:
            if f in fields and not isinstance(fields[f], str):
                fields[f] = json.dumps(fields[f])
        if "website" in fields:
            fields["domain"] = dedupe_domain(fields["website"])
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE businesses SET {sets} WHERE id = ?", (*fields.values(), biz_id))
        self.conn.commit()

    def businesses(self, campaign: str | None = None, where: str = "", params: Iterable[Any] = ()) -> list[dict]:
        sql = "SELECT * FROM businesses WHERE 1=1"
        args: list[Any] = []
        if campaign:
            sql += " AND campaign = ?"
            args.append(campaign)
        if where:
            sql += f" AND ({where})"
            args.extend(params)
        sql += " ORDER BY COALESCE(score, -1) DESC, id"
        return [self._decode(r) for r in self.conn.execute(sql, args)]

    def business(self, biz_id: int) -> dict:
        return self._decode(self.conn.execute("SELECT * FROM businesses WHERE id = ?", (biz_id,)).fetchone())

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        d = dict(row)
        for f in JSON_FIELDS:
            d[f] = json.loads(d.get(f) or ("[]" if f == "signals" else "{}"))
        return d

    # ---------- messages ----------
    def add_message(self, business_id: int, channel: str, body: str, subject: str | None = None,
                    step: int = 0, status: str = "draft", scheduled_at: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO messages (business_id, channel, step, subject, body, status, scheduled_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (business_id, channel, step, subject, body, status, scheduled_at, now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def messages(self, where: str = "1=1", params: Iterable[Any] = ()) -> list[dict]:
        sql = ("SELECT m.*, b.name AS business_name, b.email AS business_email, b.phone AS business_phone,"
               " b.campaign AS campaign, b.status AS business_status"
               " FROM messages m JOIN businesses b ON b.id = m.business_id"
               f" WHERE {where} ORDER BY m.id")
        return [dict(r) for r in self.conn.execute(sql, tuple(params))]

    def update_message(self, msg_id: int, **fields: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE messages SET {sets} WHERE id = ?", (*fields.values(), msg_id))
        self.conn.commit()

    def has_messages(self, business_id: int) -> bool:
        return self.conn.execute("SELECT 1 FROM messages WHERE business_id = ?", (business_id,)).fetchone() is not None

    def sent_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE channel = 'email' AND status = 'sent' AND sent_at >= ?",
            (today,),
        ).fetchone()[0]

    # ---------- suppression ----------
    def suppress(self, value: str, reason: str = "unsubscribed") -> None:
        self.conn.execute("INSERT OR IGNORE INTO suppression VALUES (?, ?, ?)", (value.strip().lower(), reason, now()))
        self.conn.commit()

    def is_suppressed(self, *values: str | None) -> bool:
        vals = [v.strip().lower() for v in values if v]
        if not vals:
            return False
        marks = ",".join("?" for _ in vals)
        return self.conn.execute(f"SELECT 1 FROM suppression WHERE value IN ({marks})", vals).fetchone() is not None
