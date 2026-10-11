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
from . import forms
from .jobs import STEP_HELP, STEPS, Job, JobRunner
from .security import LOCAL_HOSTS, LocalOnlyMiddleware, safe_url, same_site_path

HERE = Path(__file__).parent
STATUSES = ("new", "audited", "drafted", "contacted", "replied", "won", "lost", "unsubscribed")


def find_campaign_files(root: Path) -> list[str]:
    files = [p for p in (root / "campaign.yaml",) if p.exists()]
    files += sorted((root / "campaigns").glob("*.y*ml")) if (root / "campaigns").is_dir() else []
    return [str(p.relative_to(root)) for p in files]


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
    templates.env.globals.update(SIGNALS=SIGNALS, STEPS=STEPS, STEP_HELP=STEP_HELP, STATUSES=STATUSES,
                                 SERVICES=forms.SERVICES, CATEGORY_LABELS=forms.CATEGORY_LABELS,
                                 SOURCES=forms.SOURCES, LANGUAGES=forms.LANGUAGES)
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

    def campaign_problem(request: Request) -> str | None:
        """Why an existing campaign file can't be used, or None."""
        p = campaign_file(request)
        if not p.exists():
            return None
        try:
            load_campaign(p)
        except (ValidationError, yaml.YAMLError, OSError, TypeError) as e:
            return str(e).splitlines()[0] if str(e) else type(e).__name__
        return None

    def campaign(request: Request) -> Campaign | None:
        p = campaign_file(request)
        try:
            return load_campaign(p) if p.exists() else None
        except (ValidationError, yaml.YAMLError, OSError, TypeError):
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
    def dashboard(request: Request, welcome: int = 0):
        c = campaign(request)
        broken = campaign_problem(request)
        if forms.needs_setup(c) and not broken:  # no campaign yet, or still the example's placeholder sender
            return RedirectResponse("/setup", status_code=303)
        stats = summarize(db(request), c.name) if c else None
        queue = len(db(request).messages("m.status = 'draft' AND m.step = 0 AND b.campaign = ?", (c.name,))) if c else 0
        wa = len(pipeline.whatsapp_queue(db(request), c.name)) if c else 0
        return page(request, "dashboard.html", stats=stats, review_count=queue, whatsapp_count=wa, welcome=welcome)

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
        msgs = pipeline.whatsapp_queue(db(request), c.name)
        for m in msgs:
            m["wa_link"] = wa_link(m["business_phone"], m["body"], c.country_code)
        return page(request, "whatsapp.html", messages=msgs)

    def form_values(data: dict) -> dict:
        """Campaign data with defaults filled in, shaped for the form templates."""
        v = {"name": "", "location": "", "country_code": "", "radius_km": 5, "categories": [],
             "service": "web_design", "service_pitch": "", "language": "English", "tone": "friendly",
             "sources": ["overpass"], "llm": "auto", "min_score": 40, "auto_send": False, "pagespeed": False}
        from ..config import Limits, Sender
        v["sender"] = Sender().model_dump()
        v["limits"] = Limits().model_dump()
        for k, val in data.items():
            if k in ("sender", "limits") and isinstance(val, dict):
                v[k] = {**v[k], **{x: y for x, y in val.items() if y is not None}}
            elif val is not None:
                v[k] = val
        if "source" in data and "sources" not in data:
            v["sources"] = [data["source"]]
        v["service_custom"] = "" if v["service"] in forms.SERVICES else v["service"]
        cats = list(v.get("categories") or [])
        v["categories"] = [x for x in cats if x in forms.CATEGORY_LABELS]
        v["extra_categories"] = v.get("extra_categories") or ", ".join(x for x in cats if x not in forms.CATEGORY_LABELS)
        return v

    def yaml_of(request: Request) -> str:
        p = campaign_file(request)
        return p.read_text(encoding="utf-8") if p.exists() else ""

    @app.get("/api/geocode")
    def api_geocode(q: str = ""):
        """Find a typed place on the map (OpenStreetMap Nominatim, rate-limited and cached)."""
        from ..sources.overpass import geocode
        q = " ".join(q.split())[:200]
        if not q:
            raise HTTPException(400, "Type a place first.")
        try:
            lat, lon = geocode(q)
        except ValueError as e:
            raise HTTPException(404, str(e))
        except Exception:
            raise HTTPException(503, "Couldn't reach the map search right now. Check your internet and try again.")
        return {"lat": lat, "lon": lon}

    @app.get("/setup", response_class=HTMLResponse)
    def setup(request: Request):
        return page(request, "setup.html", v=form_values(forms.load_raw(campaign_file(request))), errors=[],
                    broken=campaign_problem(request))

    @app.post("/setup", response_class=HTMLResponse)
    async def save_setup(request: Request):
        form = await request.form()
        data, problems = forms.form_to_data(form, forms.load_raw(campaign_file(request)))
        _, errors = forms.validate(data)
        errors = problems + errors
        if errors:
            return page(request, "setup.html", v=form_values(data), errors=errors)
        forms.save_campaign(campaign_file(request), data)
        return RedirectResponse("/?welcome=1", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    def settings(request: Request, saved: int = 0):
        broken = campaign_problem(request)
        errors = [f"Your campaign file has a problem: {broken}. Fix it in the YAML editor at the bottom, "
                  "or fill in this form to replace it."] if broken else []
        return page(request, "settings.html", v=form_values(forms.load_raw(campaign_file(request))),
                    yaml_text=yaml_of(request), errors=errors, saved=bool(saved), broken=broken)

    @app.post("/settings", response_class=HTMLResponse)
    async def save_settings(request: Request):
        form = await request.form()
        data, problems = forms.form_to_data(form, forms.load_raw(campaign_file(request)))
        _, errors = forms.validate(data)
        errors = problems + errors
        if errors:
            return page(request, "settings.html", v=form_values(data), yaml_text=yaml_of(request),
                        errors=errors, saved=False)
        forms.save_campaign(campaign_file(request), data)
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/settings/yaml", response_class=HTMLResponse)
    def save_settings_yaml(request: Request, yaml_text: str = Form(...)):
        try:
            Campaign.model_validate(yaml.safe_load(yaml_text))
        except (yaml.YAMLError, ValidationError, TypeError) as e:
            raw = forms.load_raw(campaign_file(request))
            return page(request, "settings.html", v=form_values(raw), yaml_text=yaml_text,
                        errors=[f"YAML: {e}"], saved=False)
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
        port = v.get("SMTP_PORT") or "587"
        if not port.isdigit():
            return RedirectResponse("/keys?test=" + q(f"Mail server port must be a number, not '{port}'."), 303)
        error = await run_in_threadpool(test_smtp_login, v.get("SMTP_HOST") or "smtp.gmail.com",
                                        int(port), v["SMTP_USER"], v["SMTP_PASSWORD"])
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
