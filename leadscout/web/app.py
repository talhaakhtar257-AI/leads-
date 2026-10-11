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
from .security import LOCAL_HOSTS, LocalOnlyMiddleware, safe_url, same_site_path

HERE = Path(__file__).parent
STATUSES = ("new", "audited", "drafted", "contacted", "replied", "won", "lost", "unsubscribed")


def find_campaign_files(root: Path) -> list[str]:
    files = [p for p in (root / "campaign.yaml",) if p.exists()]
    files += sorted((root / "campaigns").glob("*.y*ml")) if (root / "campaigns").is_dir() else []
    return [str(p.relative_to(root)) for p in files]


# Leads that must not get any more outreach.
CLOSED = "('replied','won','lost','unsubscribed')"


def create_app(campaign_path: str = "campaign.yaml", db_path: str = "leads.db", root: str | Path = ".",
               allowed_hosts: set[str] | None = LOCAL_HOSTS) -> FastAPI:
    root = Path(root).resolve()
    env_path = root / ".env"
    load_dotenv(env_path)
    app = FastAPI(title="LeadScout", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def close_db(request: Request, call_next):
        try:
            return await call_next(request)
        finally:
            d = getattr(request.state, "db", None)
            if d is not None:
                d.close()

    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=allowed_hosts)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals.update(SIGNALS=SIGNALS, STEPS=STEPS, STATUSES=STATUSES)
    templates.env.filters["fromjson"] = json.loads
    templates.env.filters["safe_url"] = safe_url
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

    def db(request: Request) -> DB:
        """One connection per request, closed by the close_db middleware."""
        if getattr(request.state, "db", None) is None:
            request.state.db = DB(root / db_path, check_same_thread=False)
        return request.state.db

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
        b = d.business(lead_id)
        if b is None:
            raise HTTPException(404, "Lead not found")
        return b

    def back(request: Request, fallback: str = "/") -> RedirectResponse:
        return RedirectResponse(same_site_path(request.headers.get("referer"), fallback), status_code=303)

    # ----- pages -----
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        c = campaign(request)
        stats = summarize(db(request), c.name) if c else None
        queue = len(db(request).messages("m.status = 'draft' AND m.step = 0 AND b.campaign = ?", (c.name,))) if c else 0
        wa = len(db(request).messages("m.status = 'approved' AND m.channel = 'whatsapp' AND b.campaign = ?"
                                      f" AND b.status NOT IN {CLOSED}", (c.name,))) if c else 0
        return page(request, "dashboard.html", stats=stats, review_count=queue, whatsapp_count=wa)

    @app.get("/leads", response_class=HTMLResponse)
    def leads(request: Request, min_score: int = 0, status: str = "", q: str = "", new: int = 0):
        c = require_campaign(request)
        where, params = ["COALESCE(score, 0) >= ?"], [min_score]
        if status in STATUSES:
            where.append("status = ?")
            params.append(status)
        if new:
            where.append("signals LIKE '%\"new_business\"%'")
        if q:
            where.append("(name LIKE ? OR address LIKE ? OR category LIKE ?)")
            params += [f"%{q}%"] * 3
        rows = db(request).businesses(c.name, " AND ".join(where), params)
        points = [{"id": b["id"], "name": b["name"], "score": b["score"], "lat": b["lat"], "lon": b["lon"]}
                  for b in rows if b["lat"] is not None and b["lon"] is not None]
        return page(request, "leads.html", leads=rows, points=points, min_score=min_score, status=status, q=q, new=new)

    @app.get("/leads/{lead_id}", response_class=HTMLResponse)
    def lead(request: Request, lead_id: int):
        c = require_campaign(request)
        d = db(request)
        b = get_lead(d, lead_id)
        msgs = d.messages("m.business_id = ?", (lead_id,))
        for m in msgs:
            if m["channel"] == "whatsapp":
                m["wa_link"] = wa_link(b["phone"], m["body"], c.country_code)
        return page(request, "lead.html", b=b, messages=msgs)

    @app.get("/review", response_class=HTMLResponse)
    def review(request: Request):
        c = require_campaign(request)
        d = db(request)
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
        d = db(request)
        msgs = [m for m in d.messages(f"m.channel = 'whatsapp' AND m.status = 'approved' AND b.campaign = ?"
                                      f" AND b.status NOT IN {CLOSED}", (c.name,))
                if not d.is_suppressed(m["business_phone"], m["business_email"])]
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

    # ----- API keys (.env) -----
    @app.get("/keys", response_class=HTMLResponse)
    def keys(request: Request, saved: int = 0, test: str = ""):
        from ..envfile import KEYS, mask, read_env
        values = read_env(env_path)
        groups: dict[str, list] = {}
        for k in KEYS:
            current = values.get(k.name, "")
            groups.setdefault(k.group, []).append({
                "spec": k, "is_set": bool(current),
                "shown": (mask(current) if k.secret else current) or "",
                "value": "" if k.secret else (current or k.default),
            })
        return page(request, "keys.html", groups=groups, saved=bool(saved), test=test)

    async def save_key_form(request: Request) -> None:
        from ..envfile import KEYS, update_env
        form = await request.form()
        changes: dict[str, str | None] = {}
        for k in KEYS:
            if form.get(f"clear_{k.name}"):
                changes[k.name] = None
                continue
            value = (form.get(k.name) or "").strip()
            if k.secret:
                if value:  # empty secret field = keep the current value
                    changes[k.name] = value
            else:
                changes[k.name] = value or None
        update_env(env_path, changes)

    @app.post("/keys")
    async def save_keys(request: Request):
        await save_key_form(request)
        return RedirectResponse("/keys?saved=1", status_code=303)

    @app.post("/keys/test-email")
    async def test_email(request: Request):
        """Save what's in the form, then try logging in to the mail server."""
        from urllib.parse import quote as q
        from starlette.concurrency import run_in_threadpool
        from ..envfile import read_env, test_smtp_login
        await save_key_form(request)
        v = read_env(env_path)
        if not v.get("SMTP_USER") or not v.get("SMTP_PASSWORD"):
            return RedirectResponse("/keys?test=" + q("Add your Gmail address and app password first."), 303)
        error = await run_in_threadpool(test_smtp_login, v.get("SMTP_HOST") or "smtp.gmail.com",
                                        int(v.get("SMTP_PORT") or 587), v["SMTP_USER"], v["SMTP_PASSWORD"])
        return RedirectResponse("/keys?test=" + q(error or "ok"), 303)

    # ----- actions -----
    @app.post("/messages/{msg_id}")
    def update_message(request: Request, msg_id: int, action: str = Form(...),
                       body: str | None = Form(None), subject: str | None = Form(None)):
        d = db(request)
        try:
            if action in ("approve", "skip"):
                pipeline.review_message(d, msg_id, "approved" if action == "approve" else "skipped", body, subject)
            elif action == "save":
                if not d.messages("m.id = ?", (msg_id,)):
                    raise LookupError("Message not found")
                fields = {k: v.strip() for k, v in (("body", body), ("subject", subject)) if v and v.strip()}
                if fields:
                    d.update_message(msg_id, **fields)
            elif action == "whatsapp_sent":
                pipeline.mark_whatsapp_sent(d, msg_id)
            else:
                raise HTTPException(400, "Unknown action")
        except LookupError as e:
            raise HTTPException(404, str(e))
        return back(request)

    @app.post("/leads/{lead_id}/status")
    def lead_status(request: Request, lead_id: int, status: str = Form(...)):
        try:
            pipeline.set_lead_status(db(request), lead_id, status)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except LookupError as e:
            raise HTTPException(404, str(e))
        return back(request)

    @app.get("/audits/{lead_id}", response_class=HTMLResponse)
    def audit_page(request: Request, lead_id: int):
        c = require_campaign(request)
        return HTMLResponse(render_audit_html(get_lead(db(request), lead_id), c))

    @app.get("/export.csv")
    def export_csv(request: Request):
        import csv
        from ..export.csv import COLUMNS, lead_rows, safe_rows
        c = require_campaign(request)
        buf = io.StringIO()
        buf.write("﻿")  # Excel-friendly UTF-8
        w = csv.DictWriter(buf, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(safe_rows(lead_rows(db(request), c)))
        name = quote(f"{c.name}.csv")
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})

    @app.get("/pack.zip")
    def download_pack(request: Request, niche: str = "", min_score: int = 40, business_emails_only: int = 0):
        from fastapi.responses import FileResponse
        from ..export.pack import build_pack
        c = require_campaign(request)
        try:
            path = build_pack(db(request), c, niche or None, min_score, bool(business_emails_only),
                              out_dir=root / "output" / "packs")
        except ValueError as e:
            raise HTTPException(404, str(e))
        except RuntimeError as e:
            raise HTTPException(500, str(e))
        return FileResponse(path, media_type="application/zip", filename=path.name)

    # ----- background jobs -----
    @app.post("/jobs/{step}")
    def start_job(request: Request, step: str):
        if step not in STEPS:
            raise HTTPException(404, "Unknown step")
        c = require_campaign(request)
        db_file = root / db_path

        def work(job: Job) -> None:
            if step in ("run", "discover", "send"):
                from ..backup import backup_db
                saved = backup_db(db_file)
                if saved:
                    job.log(f"Backed up your leads to {saved.name}")
            with DB(db_file) as d:  # own connection: SQLite connections stay on their thread
                run_step(d, job.log)

        def run_step(d: DB, log) -> None:
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
