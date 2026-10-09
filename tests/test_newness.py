from datetime import date

from leadscout.audit.newness import is_new, newness_evidence
from leadscout.audit.website import audit_business
from leadscout.outreach.drafts import template_draft
from leadscout.scoring import score_lead
from leadscout.signals import describe
from leadscout.sources.overpass import parse_elements

TODAY = date(2026, 10, 9)


def test_start_date_rules():
    assert is_new({"meta": {"start_date": "2026-03"}}, TODAY)
    assert is_new({"meta": {"opening_date": "2026-09-01"}}, TODAY)
    assert not is_new({"meta": {"start_date": "2019"}}, TODAY)
    assert not is_new({"meta": {"start_date": "2027-01"}}, TODAY)  # future: not open yet
    assert not is_new({"meta": {"start_date": "garbage"}}, TODAY)


def test_osm_first_version_rules():
    assert newness_evidence({"meta": {"osm_version": 1, "osm_timestamp": "2026-07-01T10:00:00Z"}}, TODAY)
    assert not is_new({"meta": {"osm_version": 7, "osm_timestamp": "2026-07-01T10:00:00Z"}}, TODAY)  # old, just edited
    assert not is_new({"meta": {"osm_version": 1, "osm_timestamp": "2024-01-01T10:00:00Z"}}, TODAY)


def test_review_count_rule_only_for_google():
    assert is_new({"source": "google_places", "review_count": 3}, TODAY)
    assert not is_new({"source": "google_places", "review_count": 40}, TODAY)
    assert not is_new({"source": "osm", "review_count": 3}, TODAY)


def test_overpass_keeps_metadata():
    data = {"elements": [{"type": "node", "id": 9, "lat": 1, "lon": 2, "version": 1,
                          "timestamp": "2026-08-01T00:00:00Z",
                          "tags": {"name": "Fresh Cafe", "start_date": "2026-07"}}]}
    meta = parse_elements(data, "cafe")[0]["meta"]
    assert meta == {"osm_version": 1, "osm_timestamp": "2026-08-01T00:00:00Z", "start_date": "2026-07"}


def test_new_business_signal_scores_and_congratulates(campaign):
    biz = {"name": "Fresh Cafe", "website": None, "phone": "123", "email": "a@fresh.pk",
           "meta": {"start_date": date.today().strftime("%Y-%m")}}
    biz["signals"] = audit_business(biz)["signals"]
    assert "new_business" in biz["signals"] and "no_website" in biz["signals"]
    assert score_lead(biz, "web_design") == 45 + 25 + 15
    d = template_draft(biz, campaign, describe(["no_website", "new_business"]))
    assert d["email"].startswith("Hi Fresh Cafe team,\n\nCongratulations on opening Fresh Cafe!")
    assert "noticed: no website" in d["email"]  # the problem, not "recently opened", is the hook
    assert d["whatsapp"].startswith("Hi! Congrats on the new opening!")
