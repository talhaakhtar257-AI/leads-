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


def discover(db: DB, campaign: Campaign, limit: int | None = None, log: Log = print) -> int:
    if campaign.source == "google_places":
        from .sources.google_places import discover as find
        found = find(campaign.location, campaign.categories)
    else:
        from .sources.overpass import discover as find
        found = find(campaign.location, campaign.categories, campaign.radius_km)
    added = dupes = 0
    for biz in found:
        if limit is not None and added >= limit:
            break
        if db.insert_business(campaign.name, biz):
            added += 1
        else:
            dupes += 1
    log(f"Discovered {len(found)} businesses: {added} new, {dupes} already known (skipped).")
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
