import smtplib

import pytest

from leadscout import pipeline
from leadscout.db import now
from leadscout.export.csv import csv_safe
from leadscout.outreach import email_sender
from leadscout.outreach.drafts import draft_for
from leadscout.outreach.followups import is_unsubscribe, record_reply, strip_quoted
from leadscout.web.security import safe_url, same_site_path


def test_safe_url():
    assert safe_url("javascript:alert(1)") == "#"
    assert safe_url(" JavaScript:alert(1)") == "#"
    assert safe_url("data:text/html,x") == "#"
    assert safe_url("https://chai.pk/menu") == "https://chai.pk/menu"
    assert safe_url("chai.pk") == "http://chai.pk"
    assert safe_url("mailto:a@b.pk") == "mailto:a@b.pk"
    assert safe_url(None) == "#"


def test_same_site_path_never_redirects_offsite():
    assert same_site_path("http://localhost:8000/leads?q=x") == "/leads?q=x"
    assert same_site_path("https://evil.example//evil.example/x") == "/"
    assert same_site_path(None, "/review") == "/review"


def test_csv_formula_escaping():
    assert csv_safe('=HYPERLINK("http://evil","x")').startswith("'=")
    assert csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert csv_safe("+92 300 1234567") == "+92 300 1234567"  # phone stays usable
    assert csv_safe("-5") == "-5"
    assert csv_safe("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert csv_safe(None) is None and csv_safe(42) == 42


QUOTED_OUTLOOK = """Yes please, send the audit!

From: Your Name <you@example.com>
Sent: Monday
Subject: Quick idea
Not interested? Reply "unsubscribe" and I won't contact you again."""

QUOTED_GERMAN = """Gerne, schicken Sie es.

Am Mo., 6. Okt. 2026 um 10:00 schrieb Your Name <you@example.com>:
> Not interested? Reply "unsubscribe" and I won't contact you again."""


def test_quoted_footer_is_not_an_unsubscribe():
    for body in (QUOTED_OUTLOOK, QUOTED_GERMAN):
        top = strip_quoted(body)
        assert "unsubscribe" not in top.lower()
        assert not is_unsubscribe(top)
    assert is_unsubscribe(strip_quoted("Please unsubscribe me.\n\nOn Mon, Your Name wrote:\n> hi"))


def test_record_reply_cancels_pending_whatsapp_too(db, campaign, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    campaign.llm = "template"
    bid = db.insert_business(campaign.name, {"name": "Chai", "phone": "03001234567"})
    db.update_business(bid, email="a@chai.pk", signals=["no_website"], score=60, status="audited", audited_at=now())
    pipeline.draft(db, campaign, log=lambda *_: None)
    db.conn.execute("UPDATE messages SET status = 'approved'")
    db.conn.commit()
    record_reply(db, bid, "a@chai.pk", "please unsubscribe")
    assert {m["status"] for m in db.messages("m.business_id = ?", (bid,))} == {"cancelled"}


def test_phone_suppression_matches_any_format(db):
    db.suppress("03001234567")
    assert db.is_suppressed("+92 300 1234567")
    assert db.is_suppressed("0092-300-1234567")
    assert not db.is_suppressed("+92 300 7654321")


def test_same_name_branches_are_not_merged(db):
    a = db.insert_business("c", {"name": "Subway", "lat": 31.500, "lon": 74.300})
    b = db.insert_business("c", {"name": "Subway", "lat": 31.560, "lon": 74.350})
    c = db.insert_business("c", {"name": "Subway"})  # nothing to tell branches apart: still kept
    assert a and b and c


def test_unknown_ids_are_lookup_errors(db):
    assert db.business(999) is None
    with pytest.raises(LookupError):
        pipeline.set_lead_status(db, 999, "won")
    with pytest.raises(LookupError):
        pipeline.review_message(db, 999, "approved")


def test_bad_website_does_not_stop_audit(db, campaign, monkeypatch):
    import leadscout.pipeline as pl
    for name in ("Good Cafe", "Broken Cafe"):
        db.insert_business(campaign.name, {"name": name, "phone": "0300 1111111" if name[0] == "G" else "0300 2222222"})

    def fake_audit(b, use_pagespeed=False):
        if b["name"] == "Broken Cafe":
            raise UnicodeError("label too long")
        return {"signals": ["no_website"], "details": {}, "email": None, "phone": b["phone"], "socials": {}}

    monkeypatch.setattr(pl, "audit_business", fake_audit)
    lines = []
    assert pl.audit(db, campaign, log=lines.append) == 2
    broken = db.businesses(where="name = 'Broken Cafe'")[0]
    assert broken["audit"]["error"].startswith("UnicodeError") and broken["audited_at"]
    assert db.businesses(where="name = 'Good Cafe'")[0]["signals"] == ["no_website"]
    assert pl.audit(db, campaign, log=lines.append) == 0  # nothing left to retry


def test_invalid_url_is_site_down():
    from leadscout.audit.website import audit_business
    r = audit_business({"name": "X", "website": "http://exa mple.com:abc/", "phone": "1"})
    assert "site_down" in r["signals"]


def test_llm_crash_falls_back_to_template(campaign):
    class Boom:
        name = "boom"

        def generate(self, *a, **k):
            raise TimeoutError("read timeout")

    d = draft_for({"id": 1, "name": "Chai", "signals": ["no_website"]}, campaign, Boom())
    assert d["subject"] == "Quick idea for Chai"


def test_one_rejected_address_does_not_block_queue(db, campaign, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    campaign.llm = "template"
    for i, email in enumerate(("bad@x.pk", "good@y.pk")):
        bid = db.insert_business(campaign.name, {"name": f"Lead {i}", "phone": f"0300 000000{i}"})
        db.update_business(bid, email=email, signals=["no_website"], score=60, status="audited", audited_at=now())
    pipeline.draft(db, campaign, log=lambda *_: None)
    db.conn.execute("UPDATE messages SET status = 'approved' WHERE channel = 'email'")
    db.conn.commit()
    sent = []

    class FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def send(self, msg):
            if msg["To"] == "bad@x.pk":
                raise smtplib.SMTPRecipientsRefused({"bad@x.pk": (550, b"no such user")})
            sent.append(msg["To"])

    monkeypatch.setattr(email_sender, "SMTPSender", FakeSMTP)
    assert email_sender.send_due(db, campaign, log=lambda *_: None, sleep=lambda s: None) == 1
    assert sent == ["good@y.pk"]
    statuses = {m["business_email"]: m["status"] for m in db.messages("m.channel = 'email' AND m.step = 0")}
    assert statuses == {"bad@x.pk": "failed", "good@y.pk": "sent"}
