"""Reply detection over IMAP: stop follow-ups when a lead replies, honor unsubscribes."""
from __future__ import annotations

import email
import imaplib
import os
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from typing import Callable

from ..db import DB

UNSUB_WORDS = ("unsubscribe", "remove me", "not interested", "don't contact", "do not contact")


def cancel_followups(db: DB, business_id: int) -> None:
    db.conn.execute(
        "UPDATE messages SET status = 'cancelled' WHERE business_id = ? AND step > 0 AND status IN ('approved','scheduled','draft')",
        (business_id,),
    )
    db.conn.commit()


def is_unsubscribe(text: str) -> bool:
    t = text.lower()
    if any(w in t for w in UNSUB_WORDS):
        return True
    # A bare "STOP" reply (common on WhatsApp/SMS) also counts.
    return any(line.strip(" .!").lower() == "stop" for line in text.splitlines())


def _text_of(msg: email.message.Message) -> str:
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    parts = []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            parts.append(payload.decode(part.get_content_charset() or "utf-8", "replace"))
    # Only the top of the reply matters; quoted original text contains our own footer.
    body = "\n".join(parts).split("\nOn ")[0].split("\n>")[0]
    return f"{subject}\n{body[:2000]}"


def record_reply(db: DB, business_id: int, from_addr: str, text: str) -> str:
    cancel_followups(db, business_id)
    if is_unsubscribe(text):
        db.suppress(from_addr, "unsubscribed")
        db.update_business(business_id, status="unsubscribed")
        return "unsubscribed"
    db.update_business(business_id, status="replied")
    return "replied"


def check_replies(db: DB, days: int = 30, log: Callable[[str], None] = print) -> int:
    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    user = os.environ.get("IMAP_USER") or os.environ.get("SMTP_USER", "")
    password = os.environ.get("IMAP_PASSWORD") or os.environ.get("SMTP_PASSWORD", "")
    if not user or not password:
        raise RuntimeError("Set IMAP_USER/IMAP_PASSWORD (or SMTP_USER/SMTP_PASSWORD) in .env")

    contacted = {b["email"].lower(): b for b in db.businesses(where="status = 'contacted' AND email IS NOT NULL")}
    if not contacted:
        log("No contacted leads to check.")
        return 0
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    found = 0
    box = imaplib.IMAP4_SSL(host)
    try:
        box.login(user, password)
        box.select("INBOX", readonly=True)
        for addr, biz in contacted.items():
            typ, data = box.search(None, "FROM", f'"{addr}"', "SINCE", since)
            ids = data[0].split() if typ == "OK" and data and data[0] else []
            if not ids:
                continue
            typ, msg_data = box.fetch(ids[-1], "(RFC822)")
            raw = msg_data[0][1] if typ == "OK" and msg_data and msg_data[0] else b""
            text = _text_of(email.message_from_bytes(raw)) if raw else ""
            result = record_reply(db, biz["id"], addr, text)
            log(f"{biz['name']}: {result}")
            found += 1
    finally:
        try:
            box.logout()
        except Exception:
            pass
    return found
