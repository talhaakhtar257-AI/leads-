"""Render a one-page audit per lead: the evidence behind the pitch."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from ..config import Campaign
from ..signals import describe

_env = Environment(loader=PackageLoader("leadscout.reports", "templates"), autoescape=select_autoescape())


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "lead"


def render_audit_html(biz: dict[str, Any], campaign: Campaign) -> str:
    return _env.get_template("audit.html").render(
        biz=biz, findings=describe(biz.get("signals") or []), sender=campaign.sender, date=date.today().isoformat(),
    )


def render_audit(biz: dict[str, Any], campaign: Campaign, out_dir: str | Path = "output/audits") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html = render_audit_html(biz, campaign)
    path = out / f"{biz['id']}-{slug(biz['name'])}.html"
    path.write_text(html, encoding="utf-8")
    return path
