"""LeadScout web dashboard (local). Start with: leadscout web"""
from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.parse import quote

import yaml
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from .. import pipeline
from ..config import Campaign, load_campaign, load_dotenv
from ..db import DB
from ..outreach.whatsapp import wa_link
from ..reports.audit_page import render_audit_html
from ..reports.campaign import summarize
from ..signals import SIGNALS
from .jobs import STEPS, Job, JobRunner

HERE = Path(__file__).parent
STATUSES = ("new", "audited", "drafted", "contacted", "replied", "won", "lost", "unsubscribed")


def find_campaign_files(root: Path) -> list[str]:
    files = [p for p in (root / "campaign.yaml",) if p.exists()]
    files += sorted((root / "campaigns").glob("*.y*ml")) if (root / "campaigns").is_dir() else []
    return [str(p.relative_to(root)) for p in files]


def create_app(campaign_path: str = "campaign.yaml", db_path: str = "leads.db", root: str | Path = ".") -> FastAPI:
    load_dotenv()
    root = Path(root).resolve()
    app = FastAPI(title="LeadScout", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals.update(SIGNALS=SIGNALS, STEPS=STEPS, STATUSES=STATUSES)
    templates.env.filters["fromjson"] = json.loads
    runner = JobRunner()
    app.state.runner = runner

    # ----- helpers -----
    def campaign_file(request: Request) -> Path:
        chosen = request.cookies.get("campaign") or campaign_path
        allowed = set(find_campaign_files(root)) | {campaign_path}
        if chosen not in allowed:
            chosen = campaign_path
        return root / chosen

    def campaign(request: Request) -> Campaign | None:
        p = campaign_file(request)
        try:
            return load_campaign(p) if p.exists() else None
        except (ValidationError, yaml.YAMLError, OSError):
            return None

    def db() -> DB:
        return DB(root / db_path)

    def page(request: Request, name: str, **ctx) -> HTMLResponse:
        c = campaign(request)
        ctx.update(request=request, campaign=c, campaign_file=str(campaign_file(request).relative_to(root)),
                   campaign_files=find_campaign_files(root) or [campaign_path], job=runner.current,
                   busy=runner.busy())
        return templates.TemplateResponse(request, name, ctx)

    def require_campaign(request: Request) -> Campaign:
        c = campaign(request)
        if c is None:
            raise HTTPException(400, "No valid campaign file. Open Settings to create one.")
        return c

    def get_lead(d: DB, lead_id: int) -> dict:
        row = d.conn.execute("SELECT 1 FROM businesses WHERE id = ?", (lead_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Lead not found")
        return d.business(lead_id)

    def back(request: Request, fallback: str = "/") -> RedirectResponse:
        ref = request.headers.get("referer") or fallback
        return RedirectResponse(ref, status_code=303)

    # ----- pages -----
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        c = campaign(request)
        stats = summarize(db(), c.name) if c else None
        queue = len(db().messages("m.status = 'draft' AND m.step = 0 AND b.campaign = ?", (c.name,))) if c else 0
        wa = len(db().messages("m.status = 'approved' AND m.channel = 'whatsapp' AND b.campaign = ?", (c.name,))) if c else 0
        return page(request, "dashboard.html", stats=stats, review_count=queue, whatsapp_count=wa)

    @app.get("/leads", response_class=HTMLResponse)
    def leads(request: Request, min_score: int = 0, status: str = "", q: str = ""):
        c = require_campaign(request)
        where, params = ["COALESCE(score, 0) >= ?"], [min_score]
        if status in STATUSES:
            where.append("status = ?")
            params.append(status)
        if q:
            where.append("(name LIKE ? OR address LIKE ? OR category LIKE ?)")
            params += [f"%{q}%"] * 3
        rows = db().businesses(c.name, " AND ".join(where), params)
        points = [{"id": b["id"], "name": b["name"], "score": b["score"], "lat": b["lat"], "lon": b["lon"]}
                  for b in rows if b["lat"] is not None and b["lon"] is not None]
        return page(request, "leads.html", leads=rows, points=points, min_score=min_score, status=status, q=q)

    @app.get("/leads/{lead_id}", response_class=HTMLResponse)
    def lead(request: Request, lead_id: int):
        c = require_campaign(request)
        d = db()
        b = get_lead(d, lead_id)
        msgs = d.messages("m.business_id = ?", (lead_id,))
        for m in msgs:
            if m["channel"] == "whatsapp":
                m["wa_link"] = wa_link(b["phone"], m["body"], c.country_code)
        return page(request, "lead.html", b=b, messages=msgs)

    @app.get("/review", response_class=HTMLResponse)
    def review(request: Request):
        c = require_campaign(request)
        d = db()
        drafts = d.messages("m.status = 'draft' AND m.step = 0 AND b.campaign = ?", (c.name,))
        items = []
        for m in drafts:
            b = d.business(m["business_id"])
            follow = d.messages("m.business_id = ? AND m.channel = ? AND m.step > 0 AND m.status = 'draft'",
                                (b["id"], m["channel"]))
            items.append({"m": m, "b": b, "followups": follow})
        return page(request, "review.html", items=items)

    @app.get("/whatsapp", response_class=HTMLResponse)
    def whatsapp(request: Request):
        c = require_campaign(request)
        msgs = db().messages("m.channel = 'whatsapp' AND m.status = 'approved' AND b.campaign = ?", (c.name,))
        for m in msgs:
            m["wa_link"] = wa_link(m["business_phone"], m["body"], c.country_code)
        return page(request, "whatsapp.html", messages=msgs)

    @app.get("/settings", response_class=HTMLResponse)
    def settings(request: Request, saved: int = 0):
        p = campaign_file(request)
        text = p.read_text(encoding="utf-8") if p.exists() else (root / "campaigns" / "example.yaml").read_text(encoding="utf-8") \
            if (root / "campaigns" / "example.yaml").exists() else ""
        return page(request, "settings.html", yaml_text=text, error=None, saved=bool(saved))

    @app.post("/settings", response_class=HTMLResponse)
    def save_settings(request: Request, yaml_text: str = Form(...)):
        try:
            Campaign.model_validate(yaml.safe_load(yaml_text))
        except (yaml.YAMLError, ValidationError, TypeError) as e:
            return page(request, "settings.html", yaml_text=yaml_text, error=str(e), saved=False)
        campaign_file(request).write_text(yaml_text, encoding="utf-8")
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/campaign")
    def switch_campaign(request: Request, file: str = Form(...)):
        resp = back(request)
        if file in find_campaign_files(root):
            resp.set_cookie("campaign", file, samesite="strict")
        return resp

    # ----- actions -----
    @app.post("/messages/{msg_id}")
    def update_message(request: Request, msg_id: int, action: str = Form(...),
                       body: str | None = Form(None), subject: str | None = Form(None)):
        d = db()
        if action in ("approve", "skip"):
            pipeline.review_message(d, msg_id, "approved" if action == "approve" else "skipped", body, subject)
        elif action == "save":
            fields = {k: v.strip() for k, v in (("body", body), ("subject", subject)) if v and v.strip()}
            if fields:
                d.update_message(msg_id, **fields)
        elif action == "whatsapp_sent":
            pipeline.mark_whatsapp_sent(d, msg_id)
        else:
            raise HTTPException(400, "Unknown action")
        return back(request)

    @app.post("/leads/{lead_id}/status")
    def lead_status(request: Request, lead_id: int, status: str = Form(...)):
        try:
            pipeline.set_lead_status(db(), lead_id, status)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return back(request)

    @app.get("/audits/{lead_id}", response_class=HTMLResponse)
    def audit_page(request: Request, lead_id: int):
        c = require_campaign(request)
        return HTMLResponse(render_audit_html(get_lead(db(), lead_id), c))

    @app.get("/export.csv")
    def export_csv(request: Request):
        import csv
        from ..export.csv import COLUMNS, lead_rows
        c = require_campaign(request)
        buf = io.StringIO()
        buf.write("﻿")  # Excel-friendly UTF-8
        w = csv.DictWriter(buf, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(lead_rows(db(), c))
        name = quote(f"{c.name}.csv")
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})

    # ----- background jobs -----
    @app.post("/jobs/{step}")
    def start_job(request: Request, step: str):
        if step not in STEPS:
            raise HTTPException(404, "Unknown step")
        c = require_campaign(request)
        db_file = root / db_path

        def work(job: Job) -> None:
            d = DB(db_file)  # own connection: SQLite connections stay on their thread
            log = job.log
            if step in ("run", "discover"):
                pipeline.discover(d, c, log=log)
            if step in ("run", "audit"):
                pipeline.audit(d, c, log=log)
            if step in ("run", "score"):
                pipeline.score(d, c, log)
            if step in ("run", "draft"):
                pipeline.draft(d, c, log=log)
            if step in ("send", "send_dry"):
                from ..outreach.email_sender import send_due
                n = send_due(d, c, dry_run=step == "send_dry", log=log)
                log(f"{'Would send' if step == 'send_dry' else 'Sent'} {n} email(s).")
            if step == "check_replies":
                from ..outreach.followups import check_replies
                log(f"{check_replies(d, log=log)} lead(s) replied.")

        try:
            runner.start(step, work)
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(runner.current.as_dict())
        return RedirectResponse("/", status_code=303)

    @app.get("/api/job")
    def job_status():
        return runner.current.as_dict() if runner.current else {}

    return app
