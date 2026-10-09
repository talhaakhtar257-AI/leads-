import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from leadscout import pipeline  # noqa: E402
from leadscout.db import DB, now  # noqa: E402
from leadscout.web.app import create_app  # noqa: E402

CAMPAIGN_YAML = """
name: webtest
location: Lahore
country_code: "92"
categories: [cafe]
service: web_design
llm: template
min_score: 30
"""


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "campaign.yaml").write_text(CAMPAIGN_YAML)
    d = DB(tmp_path / "leads.db")
    bid = d.insert_business("webtest", {"name": "Chai Corner", "phone": "03001234567", "lat": 31.5, "lon": 74.3})
    d.update_business(bid, email="info@chai.pk", signals=["no_website"], score=60, status="audited", audited_at=now())
    from leadscout.config import load_campaign
    pipeline.draft(d, load_campaign(tmp_path / "campaign.yaml"), log=lambda *_: None)
    client = TestClient(create_app("campaign.yaml", "leads.db", root=tmp_path))
    return client, d, bid


def test_pages_render(site):
    client, d, bid = site
    for path in ("/", "/leads", f"/leads/{bid}", "/review", "/whatsapp", "/settings", f"/audits/{bid}"):
        r = client.get(path)
        assert r.status_code == 200, path
    assert "Chai Corner" in client.get("/leads").text
    assert "No website" in client.get(f"/leads/{bid}").text
    assert client.get("/leads/999").status_code == 404


def test_leads_filters(site):
    client, _, _ = site
    assert "Chai Corner" in client.get("/leads?q=chai&min_score=40").text
    assert "Chai Corner" not in client.get("/leads?min_score=80").text
    assert "Chai Corner" not in client.get("/leads?status=won").text


def test_approve_from_review_cascades_to_followups(site):
    client, d, bid = site
    first = d.messages("m.business_id = ? AND m.channel = 'email' AND m.step = 0", (bid,))[0]
    r = client.post(f"/messages/{first['id']}", data={"action": "approve", "body": "Edited body", "subject": "New subj"},
                    follow_redirects=False)
    assert r.status_code == 303
    msgs = {m["step"]: m for m in d.messages("m.business_id = ? AND m.channel = 'email'", (bid,))}
    assert msgs[0]["body"] == "Edited body" and msgs[0]["subject"] == "New subj"
    assert all(m["status"] == "approved" for m in msgs.values())


def test_whatsapp_queue_and_mark_sent(site):
    client, d, bid = site
    wa = d.messages("m.business_id = ? AND m.channel = 'whatsapp'", (bid,))[0]
    client.post(f"/messages/{wa['id']}", data={"action": "approve"})
    assert "https://wa.me/923001234567?text=" in client.get("/whatsapp").text
    client.post(f"/messages/{wa['id']}", data={"action": "whatsapp_sent"})
    assert d.business(bid)["status"] == "contacted"


def test_lead_status_and_unsubscribe(site):
    client, d, bid = site
    client.post(f"/leads/{bid}/status", data={"status": "unsubscribed"})
    assert d.business(bid)["status"] == "unsubscribed"
    assert d.is_suppressed("info@chai.pk")
    assert client.post(f"/leads/{bid}/status", data={"status": "bogus"}).status_code == 400


def test_settings_validates_before_saving(site, tmp_path):
    client, _, _ = site
    r = client.post("/settings", data={"yaml_text": "name: x\n"})  # missing location/categories
    assert "Not saved" in r.text
    assert "webtest" in (tmp_path / "campaign.yaml").read_text()
    new = CAMPAIGN_YAML.replace("min_score: 30", "min_score: 50")
    r = client.post("/settings", data={"yaml_text": new}, follow_redirects=False)
    assert r.status_code == 303 and "min_score: 50" in (tmp_path / "campaign.yaml").read_text()


def test_export_csv(site):
    client, _, _ = site
    r = client.get("/export.csv")
    assert r.status_code == 200 and "Chai Corner" in r.text and "wa.me/92" in r.text


def test_background_job_runs_and_logs(site):
    client, _, _ = site
    r = client.post("/jobs/score", headers={"Accept": "application/json"})
    assert r.status_code == 200
    for _ in range(50):
        job = client.get("/api/job").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done"
    assert any("Scored" in line for line in job["lines"])
    assert client.post("/jobs/nope").status_code == 404
