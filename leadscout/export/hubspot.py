"""Push leads to HubSpot's free CRM as companies (private app token in HUBSPOT_TOKEN,
scopes: crm.objects.companies.read + write)."""
from __future__ import annotations

import os
from typing import Callable

from ..config import Campaign
from ..db import DB
from ..http import client
from .csv import lead_rows

API = "https://api.hubapi.com/crm/v3/objects/companies"


def export_hubspot(db: DB, campaign: Campaign, min_score: int = 0, log: Callable[[str], None] = print) -> int:
    token = os.environ.get("HUBSPOT_TOKEN")
    if not token:
        raise RuntimeError("Set HUBSPOT_TOKEN (HubSpot private app token)")
    headers = {"Authorization": f"Bearer {token}"}
    created = 0
    with client() as c:
        for r in lead_rows(db, campaign):
            if (r["score"] or 0) < min_score:
                continue
            props = {
                "name": r["name"],
                "phone": r["phone"] or "",
                "website": r["website"] or "",
                "address": r["address"] or "",
                "description": f"LeadScout score {r['score']}. {r['reason'] or ''} Problems: {r['problems']}"[:5000],
            }
            resp = c.post(API, json={"properties": props}, headers=headers)
            if resp.status_code < 300:
                created += 1
            else:
                log(f"HubSpot rejected {r['name']}: {resp.status_code} {resp.text[:200]}")
    return created
