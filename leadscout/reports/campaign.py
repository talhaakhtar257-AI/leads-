"""Campaign summary: funnel numbers and which problems are most common."""
from __future__ import annotations

from collections import Counter
from typing import Any

from ..db import DB
from ..signals import SIGNALS


def summarize(db: DB, campaign: str) -> dict[str, Any]:
    leads = db.businesses(campaign)
    statuses = Counter(b["status"] for b in leads)
    signals = Counter(s for b in leads for s in b["signals"])
    msgs = db.messages("b.campaign = ?", (campaign,))
    sent = sum(1 for m in msgs if m["status"] == "sent" and m["channel"] == "email" and m["step"] == 0)
    replied = statuses.get("replied", 0) + statuses.get("won", 0) + statuses.get("lost", 0)
    scored = [b["score"] for b in leads if b["score"] is not None]
    return {
        "leads": len(leads),
        "audited": sum(1 for b in leads if b["audited_at"]),
        "with_email": sum(1 for b in leads if b["email"]),
        "with_phone": sum(1 for b in leads if b["phone"]),
        "hot_leads": sum(1 for s in scored if s >= 60),
        "avg_score": round(sum(scored) / len(scored), 1) if scored else None,
        "statuses": dict(statuses),
        "emails_sent": sent,
        "reply_rate": round(100 * replied / sent, 1) if sent else None,
        "top_problems": [
            {"signal": k, "title": SIGNALS[k].title if k in SIGNALS else k, "count": v,
             "pct": round(100 * v / len(leads), 1)}
            for k, v in signals.most_common(10)
        ],
    }
