import httpx
import pytest

import leadscout.http as lhttp
from leadscout import pipeline
from leadscout.backup import backup_db, list_backups, restore
from leadscout.db import DB
from leadscout.sources import overpass


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(lhttp, "_sleep", slept.append)
    return slept


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_retries_429_and_honours_retry_after(no_sleep):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    r = lhttp.request_with_retry(client_for(handler), "GET", "https://x.test/")
    assert r.json() == {"ok": True} and len(calls) == 3
    assert no_sleep == [7.0, 4.0]  # Retry-After, then backoff 2*2


def test_gives_up_and_returns_last_response(no_sleep):
    r = lhttp.request_with_retry(client_for(lambda req: httpx.Response(502)), "GET", "https://x.test/", attempts=3)
    assert r.status_code == 502 and len(no_sleep) == 2


def test_no_retry_on_client_errors(no_sleep):
    r = lhttp.request_with_retry(client_for(lambda req: httpx.Response(404)), "GET", "https://x.test/")
    assert r.status_code == 404 and no_sleep == []


def test_network_errors_are_retried_then_raised(no_sleep):
    def handler(request):
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(httpx.ConnectTimeout):
        lhttp.request_with_retry(client_for(handler), "GET", "https://x.test/", attempts=2)
    assert len(no_sleep) == 1


def test_overpass_falls_back_to_mirror():
    seen = []

    def handler(request):
        seen.append(request.url.host)
        if request.url.host == "overpass-api.de":
            return httpx.Response(504)
        return httpx.Response(200, json={"elements": [{"type": "node", "id": 1, "lat": 1, "lon": 2,
                                                         "tags": {"name": "Mirror Cafe"}}]})

    data = overpass.run_query(client_for(handler), "[out:json];")
    assert data["elements"][0]["tags"]["name"] == "Mirror Cafe"
    assert seen[:2] == ["overpass-api.de", "overpass-api.de"] and seen[-1] == "overpass.kumi.systems"


def test_overpass_all_down_gives_friendly_error():
    with pytest.raises(RuntimeError, match="busy or unreachable"):
        overpass.run_query(client_for(lambda req: httpx.Response(503)), "[out:json];")


def test_backup_rotation_and_restore(tmp_path):
    db_path = tmp_path / "leads.db"
    d = DB(db_path)
    d.insert_business("c", {"name": "Keep Me", "phone": "0300 1234567"})
    d.close()
    first = backup_db(db_path)
    assert first and first.exists()
    for _ in range(12):
        backup_db(db_path, keep=10)
    assert len(list_backups(db_path)) == 10
    # Lose the data, then restore it.
    d = DB(db_path)
    d.conn.execute("DELETE FROM businesses")
    d.conn.commit()
    d.close()
    safety = restore(list_backups(db_path)[0], db_path)
    assert safety and safety.exists()
    d = DB(db_path)
    assert [b["name"] for b in d.businesses()] == ["Keep Me"]
    d.close()
    assert backup_db(tmp_path / "missing.db") is None


def test_audit_resumes_where_it_stopped(db, campaign, monkeypatch):
    import leadscout.pipeline as pl
    for i in range(5):
        db.insert_business(campaign.name, {"name": f"Cafe {i}", "phone": f"0300 000000{i}"})
    audited = []

    def fake_audit(b, use_pagespeed=False):
        audited.append(b["name"])
        return {"signals": ["no_website"], "details": {}, "email": None, "phone": b["phone"], "socials": {}}

    monkeypatch.setattr(pl, "audit_business", fake_audit)
    assert pl.audit(db, campaign, limit=2, log=lambda *_: None) == 2  # "crash" after two
    lines = []
    assert pl.audit(db, campaign, log=lines.append) == 3
    assert sorted(audited) == [f"Cafe {i}" for i in range(5)]  # nobody audited twice
    assert "2 leads already checked; continuing with the 3 remaining." in lines[0]
