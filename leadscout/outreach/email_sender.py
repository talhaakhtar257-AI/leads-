"""Send approved emails over SMTP (free: Gmail app password or Brevo free tier).

Compliance built in: a daily cap, randomized delays, the suppression list,
a sender identity + postal address footer, and an unsubscribe option
(footer line + List-Unsubscribe header).
"""
from __future__ import annotations

import os
import random
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Callable

from ..config import Campaign
from ..db import DB, domain_of, now


def footer(campaign: Campaign) -> str:
    s = campaign.sender
    lines = ["", "--", s.name, s.company]
    if s.phone:
        lines.append(s.phone)
    if s.website:
        lines.append(s.website)
    lines += [s.address, "", 'Not interested? Reply "unsubscribe" and I won\'t contact you again.']
    return "\n".join(lines)


def build_message(campaign: Campaign, to: str, subject: str, body: str) -> EmailMessage:
    s = campaign.sender
    msg = EmailMessage()
    msg["From"] = f"{s.name} <{os.environ.get('SMTP_FROM') or s.email}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=domain_of(s.email) or None)
    msg["List-Unsubscribe"] = f"<mailto:{s.email}?subject=unsubscribe>"
    msg.set_content(body.rstrip() + "\n" + footer(campaign))
    return msg


class SMTPSender:
    def __init__(self) -> None:
        self.host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")
        if not self.user or not self.password:
            raise RuntimeError("Set SMTP_USER and SMTP_PASSWORD in .env (for Gmail, use an app password)")
        self.server: smtplib.SMTP | None = None

    def __enter__(self) -> "SMTPSender":
        self.server = smtplib.SMTP(self.host, self.port, timeout=30)
        self.server.starttls()
        self.server.login(self.user, self.password)
        return self

    def __exit__(self, *exc) -> None:
        if self.server:
            self.server.quit()

    def send(self, msg: EmailMessage) -> None:
        assert self.server is not None
        self.server.send_message(msg)


def due_messages(db: DB, campaign: Campaign) -> list[dict]:
    """Approved first-touch emails + follow-ups whose time has come (for leads that haven't replied)."""
    return db.messages(
        "m.channel = 'email' AND b.campaign = ? AND ("
        " (m.step = 0 AND m.status = 'approved' AND b.status NOT IN ('replied','unsubscribed','won','lost'))"
        " OR (m.step > 0 AND m.status = 'scheduled' AND m.scheduled_at <= ? AND b.status = 'contacted'))",
        (campaign.name, now()),
    )


def send_due(db: DB, campaign: Campaign, dry_run: bool = False,
             log: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep) -> int:
    queue = due_messages(db, campaign)
    budget = max(0, campaign.limits.daily_emails - db.sent_today())
    if not queue:
        log("Nothing due to send.")
        return 0
    if budget == 0 and not dry_run:
        log(f"Daily cap of {campaign.limits.daily_emails} emails reached; try again tomorrow.")
        return 0

    sent = 0
    sender = None if dry_run else SMTPSender().__enter__()
    try:
        for m in queue:
            if not dry_run and sent >= budget:
                log(f"Daily cap reached; {len(queue) - sent} message(s) left for tomorrow.")
                break
            to = m["business_email"]
            if not to or db.is_suppressed(to, domain_of(to.split("@")[-1])):
                db.update_message(m["id"], status="cancelled")
                continue
            subject = m["subject"] or f"Quick idea for {m['business_name']}"
            msg = build_message(campaign, to, subject, m["body"])
            if dry_run:
                log(f"--- DRY RUN to {to} (step {m['step']}) ---\nSubject: {subject}\n\n{msg.get_content()}")
                sent += 1
                continue
            if sent:
                sleep(random.uniform(campaign.limits.min_delay_seconds, campaign.limits.max_delay_seconds))
            sender.send(msg)
            sent += 1
            db.update_message(m["id"], status="sent", sent_at=now())
            log(f"Sent step {m['step']} to {m['business_name']} <{to}>")
            if m["step"] == 0:
                db.update_business(m["business_id"], status="contacted")
                schedule_followups(db, m["business_id"], campaign.limits.followup_days)
    finally:
        if sender:
            sender.__exit__(None, None, None)
    return sent


def schedule_followups(db: DB, business_id: int, days: list[int]) -> None:
    base = datetime.now(timezone.utc)
    for f in db.messages("m.business_id = ? AND m.channel = 'email' AND m.step > 0 AND m.status = 'approved'",
                         (business_id,)):
        offset = days[min(f["step"], len(days)) - 1] if days else 3 * f["step"]
        when = (base + timedelta(days=offset)).isoformat(timespec="seconds")
        db.update_message(f["id"], status="scheduled", scheduled_at=when)
