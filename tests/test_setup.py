import yaml
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from leadscout.config import load_campaign  # noqa: E402
from leadscout.web.app import create_app  # noqa: E402

WIZARD = {
    "service": "booking_system", "service_pitch": "I add online booking to salons.",
    "location": "DHA, Karachi, Pakistan", "radius_km": "3", "categories": ["salon", "beauty"],
    "extra_categories": "shop=tailor", "country_code": "+92",
    "sender_name": "Talha", "sender_company": "BookIt", "sender_email": "talha@bookit.pk",
    "sender_phone": "+92 300 1112223", "sender_website": "", "sender_address": "Shop 4, DHA, Karachi",
    "language": "Roman Urdu", "tone": "short",
}


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app("campaign.yaml", "leads.db", root=tmp_path)), tmp_path


def test_first_visit_goes_to_setup(fresh):
    client, _ = fresh
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/setup"
    page = client.get("/setup").text
    assert "Welcome to LeadScout" in page and "Online booking / ordering" in page and "Hair salons" in page


def test_wizard_writes_valid_campaign(fresh):
    client, root = fresh
    r = client.post("/setup", data=WIZARD, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?welcome=1"
    c = load_campaign(root / "campaign.yaml")
    assert c.service == "booking_system" and c.categories == ["salon", "beauty", "shop=tailor"]
    assert c.country_code == "92" and c.radius_km == 3 and c.language == "Roman Urdu" and c.tone == "short"
    assert c.sender.name == "Talha" and c.name == "dha-booking-system"
    assert "You're set up" in client.get("/?welcome=1").text  # no more redirect


def test_wizard_explains_missing_fields(fresh):
    client, root = fresh
    bad = {**WIZARD, "categories": [], "extra_categories": "", "location": ""}
    page = client.post("/setup", data=bad).text
    assert "Business types: pick at least one" in page and "Location:" in page
    assert not (root / "campaign.yaml").exists()


def test_placeholder_example_campaign_still_needs_setup(fresh):
    client, root = fresh
    (root / "campaign.yaml").write_text("name: x\\nlocation: L\\ncategories: [cafe]\\nsender: {name: Your Name}\\n")
    assert client.get("/", follow_redirects=False).headers["location"] == "/setup"
    assert 'value=""' in client.get("/setup").text.split('id="sender_name"')[1][:40]


def test_settings_form_keeps_fields_it_does_not_show(fresh):
    client, root = fresh
    client.post("/setup", data=WIZARD)
    data = yaml.safe_load((root / "campaign.yaml").read_text())
    data["limits"] = {"daily_emails": 30, "min_delay_seconds": 99, "max_delay_seconds": 200, "followup_days": [3, 7]}
    (root / "campaign.yaml").write_text(yaml.safe_dump(data))
    page = client.get("/settings").text
    assert "Paid" in page and "Free tier, key needed" in page and 'value="booking_system" checked' in page
    form = {**WIZARD, "advanced": "1", "sources": ["overpass", "foursquare"], "llm": "template",
            "min_score": "55", "daily_emails": "20", "followup_days": "2, 5, 9", "name": "karachi-salons"}
    r = client.post("/settings", data=form, follow_redirects=False)
    assert r.status_code == 303
    c = load_campaign(root / "campaign.yaml")
    assert c.sources == ["overpass", "foursquare"] and c.llm == "template" and c.min_score == 55
    assert c.limits.daily_emails == 20 and c.limits.followup_days == [2, 5, 9]
    assert c.limits.min_delay_seconds == 99  # kept
    assert c.name == "karachi-salons"
