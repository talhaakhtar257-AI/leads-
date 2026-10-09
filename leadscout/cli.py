"""LeadScout command line."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from . import pipeline
from .config import Campaign, load_campaign, load_dotenv
from .db import DB
from .outreach.whatsapp import wa_link
from .signals import SIGNALS

app = typer.Typer(help="LeadScout: find local businesses with fixable problems and pitch them with evidence.",
                  no_args_is_help=True)
console = Console()
log = console.print

CampaignOpt = typer.Option("campaign.yaml", "--campaign", "-c", help="Campaign YAML file")
DbOpt = typer.Option("leads.db", "--db", help="SQLite database file")
LimitOpt = typer.Option(None, "--limit", "-n", help="Max items to process")


def _load(campaign: str, db: str) -> tuple[Campaign, DB]:
    load_dotenv()
    if not Path(campaign).exists():
        log(f"[red]Campaign file {campaign} not found.[/] Run [bold]leadscout init[/] or pass -c path/to/campaign.yaml")
        raise typer.Exit(1)
    return load_campaign(campaign), DB(db)


def _discover(c: Campaign, d: DB, limit: Optional[int]) -> None:
    try:
        pipeline.discover(d, c, limit, log)
    except (httpx.HTTPError, ValueError, RuntimeError) as e:
        log(f"[red]Discovery failed:[/] {e}\nCheck your internet connection, the location name and API keys.")
        raise typer.Exit(1)


@app.command()
def init() -> None:
    """Create campaign.yaml and .env from the examples in the current folder."""
    root = Path(__file__).resolve().parent.parent
    for src, dst in ((root / "campaigns" / "example.yaml", Path("campaign.yaml")), (root / ".env.example", Path(".env"))):
        if dst.exists():
            log(f"[yellow]{dst} already exists, leaving it alone[/]")
        elif src.exists():
            shutil.copy(src, dst)
            log(f"[green]Created {dst}[/]")
    log("Edit campaign.yaml (location, categories, service, sender), then run: [bold]leadscout run[/]")


@app.command()
def run(campaign: str = CampaignOpt, db: str = DbOpt, limit: Optional[int] = LimitOpt) -> None:
    """Full pipeline: discover -> audit -> score -> draft -> export CSV."""
    c, d = _load(campaign, db)
    _discover(c, d, limit)
    pipeline.audit(d, c, limit, log=log)
    pipeline.score(d, c, log)
    pipeline.draft(d, c, log=log)
    out = _export_csv(c, d, None)
    log(f"\n[bold green]Done.[/] Leads: {out}\nNext: [bold]leadscout leads[/] to browse, [bold]leadscout review[/] to approve drafts.")


@app.command()
def discover(campaign: str = CampaignOpt, db: str = DbOpt, limit: Optional[int] = LimitOpt) -> None:
    """Find businesses (OpenStreetMap by default, or Google Places)."""
    c, d = _load(campaign, db)
    _discover(c, d, limit)


@app.command()
def audit(campaign: str = CampaignOpt, db: str = DbOpt, limit: Optional[int] = LimitOpt) -> None:
    """Audit websites and collect contacts for un-audited leads."""
    c, d = _load(campaign, db)
    pipeline.audit(d, c, limit, log=log)


@app.command()
def score(campaign: str = CampaignOpt, db: str = DbOpt) -> None:
    """Score audited leads (0-100) for the campaign's service."""
    c, d = _load(campaign, db)
    pipeline.score(d, c, log)


@app.command()
def draft(campaign: str = CampaignOpt, db: str = DbOpt, limit: Optional[int] = LimitOpt) -> None:
    """Write email + WhatsApp drafts (and follow-ups) for leads above min_score."""
    c, d = _load(campaign, db)
    pipeline.draft(d, c, limit, log)


@app.command()
def leads(campaign: str = CampaignOpt, db: str = DbOpt, min_score: int = typer.Option(0, "--min-score"),
          limit: int = typer.Option(30, "--limit", "-n")) -> None:
    """Show the best leads."""
    c, d = _load(campaign, db)
    t = Table(title=f"Leads – {c.name}")
    for col in ("id", "score", "name", "status", "problems", "email", "phone"):
        t.add_column(col, overflow="fold")
    for b in d.businesses(c.name, "COALESCE(score, 0) >= ?", (min_score,))[:limit]:
        probs = ", ".join(SIGNALS[s].title for s in b["signals"] if s in SIGNALS)
        t.add_row(str(b["id"]), str(b["score"] if b["score"] is not None else "-"), b["name"], b["status"],
                  probs, b["email"] or "", b["phone"] or "")
    console.print(t)


@app.command()
def review(campaign: str = CampaignOpt, db: str = DbOpt) -> None:
    """Approve, edit or skip each draft. Nothing is sent without approval."""
    c, d = _load(campaign, db)
    drafts = d.messages("m.status = 'draft' AND m.step = 0 AND b.campaign = ?", (c.name,))
    if not drafts:
        log("No drafts waiting for review.")
        return
    for i, m in enumerate(drafts, 1):
        b = d.business(m["business_id"])
        console.rule(f"[{i}/{len(drafts)}] {b['name']} · score {b['score']} · {m['channel']}")
        log(f"[dim]{b['reason'] or ''}[/]")
        if m["subject"]:
            log(f"[bold]Subject:[/] {m['subject']}")
        log(m["body"])
        followups = d.messages("m.business_id = ? AND m.channel = ? AND m.step > 0 AND m.status = 'draft'",
                               (b["id"], m["channel"]))
        for f in followups:
            log(f"[dim]Follow-up {f['step']}: {f['body']}[/]")
        choice = typer.prompt("[a]pprove  [e]dit  [s]kip  [q]uit", default="a").strip().lower()[:1]
        if choice == "q":
            break
        if choice == "e":
            edited = typer.edit(m["body"])
            pipeline.review_message(d, m["id"], "approved", body=edited)
            continue
        pipeline.review_message(d, m["id"], "approved" if choice == "a" else "skipped")
    log("Review finished. Send approved emails with [bold]leadscout send[/], WhatsApp with [bold]leadscout whatsapp[/].")


@app.command()
def send(campaign: str = CampaignOpt, db: str = DbOpt,
         dry_run: bool = typer.Option(False, "--dry-run", help="Print emails instead of sending")) -> None:
    """Send approved emails and due follow-ups (respects the daily cap and suppression list)."""
    from .outreach.email_sender import send_due
    c, d = _load(campaign, db)
    n = send_due(d, c, dry_run=dry_run, log=log)
    log(f"{'Would send' if dry_run else 'Sent'} {n} email(s).")


@app.command()
def whatsapp(campaign: str = CampaignOpt, db: str = DbOpt) -> None:
    """List approved WhatsApp messages as one-click wa.me links; mark them sent after you send."""
    c, d = _load(campaign, db)
    msgs = d.messages("m.channel = 'whatsapp' AND m.status = 'approved' AND b.campaign = ?", (c.name,))
    if not msgs:
        log("No approved WhatsApp messages.")
        return
    for m in msgs:
        link = wa_link(m["business_phone"], m["body"], c.country_code)
        console.rule(m["business_name"])
        log(link or f"[red]Could not build a link from phone {m['business_phone']!r} (set country_code)[/]")
        if link and typer.confirm("Mark as sent?", default=False):
            pipeline.mark_whatsapp_sent(d, m["id"])


@app.command("check-replies")
def check_replies(db: str = DbOpt, days: int = typer.Option(30, help="Look back this many days")) -> None:
    """Read your inbox (IMAP): mark replies, stop their follow-ups, honor unsubscribes."""
    load_dotenv()
    from .outreach.followups import check_replies as check
    n = check(DB(db), days, log)
    log(f"{n} lead(s) replied.")


@app.command()
def mark(lead_id: int, status: str = typer.Argument(..., help="replied | won | lost | unsubscribed"),
         db: str = DbOpt) -> None:
    """Manually set a lead's status (e.g. after a phone call or WhatsApp reply)."""
    try:
        b = pipeline.set_lead_status(DB(db), lead_id, status)
    except ValueError as e:
        raise typer.BadParameter(str(e))
    log(f"{b['name']} -> {status}")


@app.command()
def suppress(value: str, db: str = DbOpt) -> None:
    """Never contact this email, domain or phone again."""
    DB(db).suppress(value, "manual")
    log(f"Suppressed {value}")


def _export_csv(c: Campaign, d: DB, path: Optional[str]) -> Path:
    from .export.csv import export_csv
    return export_csv(d, c, path or f"output/{c.name}.csv")


@app.command()
def export(campaign: str = CampaignOpt, db: str = DbOpt,
           to: str = typer.Option("csv", help="csv | sheets | hubspot"),
           path: Optional[str] = typer.Option(None, help="CSV output path"),
           sheet_id: Optional[str] = typer.Option(None, help="Google Sheets spreadsheet ID"),
           min_score: int = typer.Option(0, help="HubSpot: only push leads at/above this score")) -> None:
    """Export leads to CSV, Google Sheets or HubSpot."""
    c, d = _load(campaign, db)
    if to == "csv":
        log(f"Wrote {_export_csv(c, d, path)}")
    elif to == "sheets":
        if not sheet_id:
            raise typer.BadParameter("--sheet-id is required for Google Sheets")
        from .export.sheets import export_sheet
        log(f"Updated {export_sheet(d, c, sheet_id)}")
    elif to == "hubspot":
        from .export.hubspot import export_hubspot
        log(f"Created {export_hubspot(d, c, min_score, log)} HubSpot companies")
    else:
        raise typer.BadParameter("--to must be csv, sheets or hubspot")


@app.command()
def pack(campaign: str = CampaignOpt, db: str = DbOpt,
         niche: Optional[str] = typer.Option(None, help="Category to include, e.g. cafe (default: all)"),
         min_score: int = typer.Option(40, help="Only leads at/above this score"),
         business_emails_only: bool = typer.Option(False, "--business-emails-only",
                                                   help="Leave out gmail/yahoo/hotmail-style addresses")) -> None:
    """Build a sellable lead pack: leads.csv + report.pdf, zipped, in output/packs/."""
    from .export.pack import build_pack
    c, d = _load(campaign, db)
    try:
        path = build_pack(d, c, niche, min_score, business_emails_only)
    except (ValueError, RuntimeError) as e:
        log(f"[red]{e}[/]")
        raise typer.Exit(1)
    log(f"[green]Lead pack ready:[/] {path}")


@app.command()
def report(campaign: str = CampaignOpt, db: str = DbOpt) -> None:
    """Campaign summary: funnel and most common problems."""
    from .reports.campaign import summarize
    c, d = _load(campaign, db)
    s = summarize(d, c.name)
    t = Table(title=f"Campaign – {c.name}", show_header=False)
    for k in ("leads", "audited", "with_email", "with_phone", "hot_leads", "avg_score", "emails_sent", "reply_rate"):
        t.add_row(k.replace("_", " "), "-" if s[k] is None else str(s[k]) + ("%" if k == "reply_rate" else ""))
    t.add_row("statuses", ", ".join(f"{k}: {v}" for k, v in s["statuses"].items()))
    console.print(t)
    p = Table(title="Most common problems")
    p.add_column("problem")
    p.add_column("leads", justify="right")
    p.add_column("%", justify="right")
    for row in s["top_problems"]:
        p.add_row(row["title"], str(row["count"]), str(row["pct"]))
    console.print(p)


@app.command()
def web(campaign: str = CampaignOpt, db: str = DbOpt,
        host: str = typer.Option("127.0.0.1", help="Use 0.0.0.0 only on a network you trust: there is no login"),
        port: int = typer.Option(8000),
        open_browser: bool = typer.Option(False, "--open", help="Open the dashboard in your browser")) -> None:
    """Open the web dashboard (run jobs, browse leads on a map, approve drafts, send WhatsApp)."""
    try:
        import uvicorn
        from .web.app import create_app
    except ImportError:
        log('[red]The dashboard needs the web extra:[/] pip install -e ".[web]"')
        raise typer.Exit(1)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    log(f"LeadScout dashboard on [bold]{url}[/] (Ctrl+C to stop)")
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(campaign, db), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
