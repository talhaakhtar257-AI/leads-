"""Lead packs: a CSV + a PDF market report per niche and area, zipped, ready to sell to agencies.

Needs the `packs` extra (fpdf2). Selling contact data is regulated in many
places (GDPR in the EU/UK, for example); check the rules where you and your
buyers operate.
"""
from __future__ import annotations

import csv
import re
import shutil
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from ..config import Campaign
from ..db import DB
from ..signals import SIGNALS
from .csv import COLUMNS, lead_rows

# Your outreach status and pre-written WhatsApp pitch stay private; buyers get the lead data.
PACK_COLUMNS = [c for c in COLUMNS if c not in ("status", "whatsapp_link")]

FREE_MAIL = ("gmail.", "googlemail.", "yahoo.", "hotmail.", "outlook.", "live.", "msn.", "aol.", "icloud.",
             "me.com", "proton", "yandex.", "mail.ru", "gmx.", "zoho.")


def is_free_mail(email: str | None) -> bool:
    domain = (email or "").rsplit("@", 1)[-1].lower()
    return bool(email) and any(domain.startswith(p) or domain == p for p in FREE_MAIL)


def select_rows(db: DB, campaign: Campaign, niche: str | None = None, min_score: int = 0,
                business_emails_only: bool = False) -> list[dict[str, Any]]:
    rows = []
    for r in lead_rows(db, campaign):
        if niche and r["category"] != niche:
            continue
        if (r["score"] or 0) < min_score or r["status"] == "unsubscribed":
            continue
        if db.is_suppressed(r["email"], r["phone"]):
            continue
        if business_emails_only and is_free_mail(r["email"]):
            r = {**r, "email": None}
        rows.append(r)
    return rows


def _latin1(text: Any) -> str:
    """The built-in PDF fonts only cover Latin-1; transliterate or replace anything else."""
    s = unicodedata.normalize("NFKD", "" if text is None else str(text))
    s = s.replace("–", "-").replace("—", "-").replace("’", "'").replace("≥", ">=")
    return s.encode("latin-1", "replace").decode("latin-1")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "all"


def write_pdf(path: Path, campaign: Campaign, rows: list[dict[str, Any]], niche: str | None,
              problem_counts: Counter, today: date) -> None:
    try:
        from fpdf import FPDF
        from fpdf.fonts import FontFace
    except ImportError as e:
        raise RuntimeError('Lead packs need the packs extra: pip install -e ".[packs]"') from e

    niche_label = (niche or "all categories").replace("_", " ")
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_title(_latin1(f"Lead pack: {niche_label}, {campaign.location}"))
    pdf.set_author(_latin1(campaign.sender.company))

    # Cover
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.ln(40)
    pdf.multi_cell(0, 12, _latin1(f"{niche_label.title()} leads" if niche else "Local business leads"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 14)
    pdf.multi_cell(0, 8, _latin1(f"{campaign.location} (within {campaign.radius_km:g} km)"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 11)
    with_email = sum(1 for r in rows if r["email"])
    with_phone = sum(1 for r in rows if r["phone"])
    hot = sum(1 for r in rows if (r["score"] or 0) >= 60)
    for line in (f"{len(rows)} businesses", f"{hot} hot leads (score 60+)",
                 f"{with_email} with email, {with_phone} with phone", f"Prepared {today.isoformat()}",
                 f"by {campaign.sender.company}"):
        pdf.multi_cell(0, 7, _latin1(line), align="C", new_x="LMARGIN", new_y="NEXT")

    # Market summary
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Market summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, _latin1(
        "Share of businesses in this pack with each problem found by the website and listing audit. "
        "Each problem is a reason a business may buy web, marketing or booking services."))
    pdf.ln(3)
    total = max(len(rows), 1)
    for key, count in problem_counts.most_common(12):
        title = SIGNALS[key].title if key in SIGNALS else key
        pct = 100 * count / total
        pdf.cell(92, 7, _latin1(title))
        x, y = pdf.get_x(), pdf.get_y()
        pdf.set_fill_color(225, 230, 240)
        pdf.rect(x, y + 2, 70, 3.5, style="F")
        pdf.set_fill_color(47, 111, 237)
        pdf.rect(x, y + 2, 70 * pct / 100, 3.5, style="F")
        pdf.set_x(x + 74)
        pdf.cell(0, 7, f"{count} ({pct:.0f}%)", new_x="LMARGIN", new_y="NEXT")

    # Lead table
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Leads", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    heading = FontFace(emphasis="BOLD", fill_color=(235, 238, 244))
    pdf.set_fill_color(255, 255, 255)
    with pdf.table(col_widths=(52, 12, 70, 56), headings_style=heading, line_height=4.2,
                   text_align=("LEFT", "CENTER", "LEFT", "LEFT"), borders_layout="HORIZONTAL_LINES",
                   cell_fill_color=(246, 247, 250), cell_fill_mode="ROWS", padding=1.2) as table:
        table.row(["Business", "Score", "Problems", "Contact"])
        for r in rows:
            contact = "\n".join(x for x in (r["email"], r["phone"], r["website"]) if x)
            name = r["name"] + (f"\n{r['address']}" if r["address"] else "")
            table.row([_latin1(name), str(r["score"] if r["score"] is not None else "-"),
                       _latin1(r["problems"] or "-"), _latin1(contact or "-")])

    # Methodology
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "How this pack was made", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _latin1(
        "Businesses come from public listings (" + ", ".join(campaign.sources) + "). Each website was checked "
        "automatically for problems such as missing HTTPS, no mobile layout, no booking and missing basic SEO. "
        "Scores (0-100) show how strongly the problems point to a need for "
        f"{campaign.service.replace('_', ' ')} and whether the business can be contacted. Contact details are "
        "public business contacts; anyone who opted out has been removed. Check local rules on business "
        "outreach and data protection before contacting these businesses."))
    pdf.output(str(path))


def build_pack(db: DB, campaign: Campaign, niche: str | None = None, min_score: int = 0,
               business_emails_only: bool = False, out_dir: str | Path = "output/packs",
               today: date | None = None) -> Path:
    """Write <out_dir>/<name>/{leads.csv, report.pdf} and <out_dir>/<name>.zip; return the zip path."""
    today = today or date.today()
    rows = select_rows(db, campaign, niche, min_score, business_emails_only)
    if not rows:
        raise ValueError("No leads match this pack (check the niche and minimum score).")
    signals_by_id = {b["id"]: b["signals"] for b in db.businesses(campaign.name)}
    problems = Counter(s for r in rows for s in signals_by_id.get(r["id"], []))

    name = f"{_slug(campaign.name)}-{_slug(niche or 'all')}-{today.isoformat()}"
    folder = Path(out_dir) / name
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "leads.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=PACK_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    write_pdf(folder / "report.pdf", campaign, rows, niche, problems, today)
    return Path(shutil.make_archive(str(folder), "zip", root_dir=folder))
