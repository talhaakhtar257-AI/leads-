"""The agent's jobs, each callable alone or chained by `leadscout run`."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .audit.website import audit_business
from .config import Campaign
from .db import DB, now
from .enrich.email_verify import verify
from .llm.base import get_llm
from .outreach.drafts import draft_for, template_reason
from .reports.audit_page import render_audit
from .scoring import relevant_signals, score_lead
from .signals import describe

Log = Callable[[str], None]


def find_businesses(campaign: Campaign, log: Log = print) -> list[dict]:
    """Query every configured source. One failing source is logged and skipped."""
    from .sources import overpass
    center: tuple[float, float] | None = None
    found: list[dict] = []
    errors: list[str] = []
    for name in campaign.sources:
        try:
            if name in ("overpass", "foursquare", "yelp") and center is None:
                center = overpass.geocode(campaign.location)
            if name == "overpass":
                batch = overpass.discover(campaign.location, campaign.categories, campaign.radius_km, center=center)
            elif name == "google_places":
                from .sources.google_places import discover as places
                batch = places(campaign.location, campaign.categories)
            elif name == "foursquare":
                from .sources.foursquare import discover as fsq
                batch = fsq(*center, campaign.categories, campaign.radius_km)
            else:
                from .sources.yelp import discover as yelp
                batch = yelp(*center, campaign.categories, campaign.radius_km)
        except Exception as e:  # keep going with the other sources
            errors.append(f"{name}: {e}")
            log(f"Source {name} failed: {e}")
            continue
        log(f"{name}: {len(batch)} businesses")
        found.extend(batch)
    if errors and len(errors) == len(campaign.sources):
        raise RuntimeError("All sources failed: " + "; ".join(errors))
    return found


def discover(db: DB, campaign: Campaign, limit: int | None = None, log: Log = print) -> int:
    found = find_businesses(campaign, log)
    added = merged = dupes = 0
    for biz in found:
        if limit is not None and added >= limit:
            break
        _, how = db.upsert_business(campaign.name, biz)
        if how == "new":
            added += 1
        elif how == "merged":
            merged += 1
        else:
            dupes += 1
    log(f"Discovered {len(found)} businesses: {added} new, {merged} enriched with extra details, "
        f"{dupes} already known.")
    return added


def audit(db: DB, campaign: Campaign, limit: int | None = None, workers: int = 8, log: Log = print) -> int:
    todo = db.businesses(campaign.name, "audited_at IS NULL")[: limit or None]

    def work(b: dict) -> tuple[dict, dict]:
        return b, audit_business(b, use_pagespeed=campaign.pagespeed)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(work, b) for b in todo]):
            b, res = fut.result()
            email = res["email"] if res["email"] and verify(res["email"]) else None
            signals = res["signals"]
            if res["email"] and not email and "no_email_found" not in signals and "no_website" not in signals:
                signals.append("no_email_found")
            db.update_business(
                b["id"], signals=signals, audit=res["details"], email=email, phone=res["phone"],
                socials=res["socials"], status="audited" if b["status"] == "new" else b["status"], audited_at=now(),
            )
            done += 1
            log(f"[{done}/{len(todo)}] {b['name']}: {', '.join(signals) or 'no issues'}")
    return done


def score(db: DB, campaign: Campaign, log: Log = print) -> int:
    leads = db.businesses(campaign.name, "audited_at IS NOT NULL")
    for b in leads:
        s = score_lead(b, campaign.service)
        # Keep the LLM-written reason once drafted; otherwise (re)derive it for the current service.
        reason = b["reason"] if b["status"] != "audited" and b["reason"] else template_reason(describe(relevant_signals(b["signals"], campaign.service)), campaign.service)
        db.update_business(b["id"], score=s, reason=reason)
    log(f"Scored {len(leads)} leads for service '{campaign.service}'.")
    return len(leads)


def draft(db: DB, campaign: Campaign, limit: int | None = None, log: Log = print) -> int:
    llm = get_llm(campaign.llm)
    log(f"Writing drafts with: {llm.name if llm else 'built-in templates (free, no API key)'}")
    leads = [b for b in db.businesses(campaign.name, "score >= ? AND status = 'audited'", (campaign.min_score,))
             if (b["email"] or b["phone"]) and not db.has_messages(b["id"])
             and not db.is_suppressed(b["email"], b["phone"])]
    leads = leads[: limit or None]
    for b in leads:
        d = draft_for(b, campaign, llm)
        if b["email"]:
            db.add_message(b["id"], "email", d["email"], subject=d["subject"], step=0)
            db.add_message(b["id"], "email", d["followup_1"], subject=f"Re: {d['subject']}", step=1)
            db.add_message(b["id"], "email", d["followup_2"], subject=f"Re: {d['subject']}", step=2)
        if b["phone"]:
            db.add_message(b["id"], "whatsapp", d["whatsapp"], step=0)
        render_audit(b, campaign)
        db.update_business(b["id"], reason=d.get("reason") or b["reason"], status="drafted")
        log(f"Drafted outreach for {b['name']} (score {b['score']})")
    if campaign.auto_send:
        db.conn.execute(
            "UPDATE messages SET status = 'approved' WHERE status = 'draft' AND business_id IN"
            " (SELECT id FROM businesses WHERE campaign = ?)", (campaign.name,))
        db.conn.commit()
        log("auto_send is on: drafts were approved without review.")
    return len(leads)


# ---------- shared actions (used by the CLI and the web dashboard) ----------

LEAD_STATUSES = ("contacted", "replied", "won", "lost", "unsubscribed")


def review_message(db: DB, msg_id: int, status: str, body: str | None = None, subject: str | None = None) -> None:
    """Approve or skip a first-touch draft; its follow-ups on the same channel follow along."""
    if status not in ("approved", "skipped"):
        raise ValueError("status must be approved or skipped")
    m = db.messages("m.id = ?", (msg_id,))[0]
    fields: dict = {"status": status}
    if body is not None and body.strip():
        fields["body"] = body.strip()
    if subject is not None and subject.strip():
        fields["subject"] = subject.strip()
    db.update_message(msg_id, **fields)
    if m["step"] == 0:
        for f in db.messages("m.business_id = ? AND m.channel = ? AND m.step > 0 AND m.status = 'draft'",
                             (m["business_id"], m["channel"])):
            db.update_message(f["id"], status=status)


def set_lead_status(db: DB, lead_id: int, status: str) -> dict:
    from .outreach.followups import cancel_followups
    if status not in LEAD_STATUSES:
        raise ValueError(f"status must be one of {', '.join(LEAD_STATUSES)}")
    b = db.business(lead_id)
    db.update_business(lead_id, status=status)
    if status != "contacted":
        cancel_followups(db, lead_id)
    if status == "unsubscribed":
        for v in (b["email"], b["phone"]):
            if v:
                db.suppress(v)
    return b


def mark_whatsapp_sent(db: DB, msg_id: int) -> None:
    m = db.messages("m.id = ? AND m.channel = 'whatsapp'", (msg_id,))[0]
    db.update_message(msg_id, status="sent", sent_at=now())
    if m["business_status"] in ("drafted", "audited"):
        db.update_business(m["business_id"], status="contacted")
