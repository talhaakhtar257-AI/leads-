import pytest

from leadscout import pipeline
from leadscout.config import Campaign
from leadscout.sources.foursquare import parse_results
from leadscout.sources.yelp import parse_businesses

FSQ = {"results": [
    {"fsq_place_id": "abc", "name": "Bean There", "latitude": 31.5, "longitude": 74.3,
     "location": {"address": "MM Alam Rd", "formatted_address": "MM Alam Rd, Lahore"},
     "tel": "042 1234567", "website": "https://beanthere.pk", "social_media": {"instagram": "beanthere"}},
    {"fsq_id": "old", "name": "Old Shape Cafe", "geocodes": {"main": {"latitude": 1.0, "longitude": 2.0}},
     "location": {"address": "Street 1"}},
    {"fsq_place_id": "x"},  # nameless: dropped
]}

YELP = {"businesses": [
    {"id": "y1", "name": "Chai Corner", "phone": "+923001234567", "rating": 3.5, "review_count": 8,
     "url": "https://www.yelp.com/biz/chai-corner?adjust_creative=x", "coordinates": {"latitude": 31.5, "longitude": 74.3},
     "location": {"display_address": ["MM Alam Rd", "Lahore"]}, "is_closed": False},
    {"id": "y2", "name": "Closed Cafe", "is_closed": True},
]}


def test_parse_foursquare_both_shapes():
    a, b = parse_results(FSQ, "cafe")
    assert a["source"] == "foursquare" and a["address"] == "MM Alam Rd, Lahore" and a["lat"] == 31.5
    assert a["socials"] == {"instagram": "https://instagram.com/beanthere"}
    assert b["source_id"] == "old" and (b["lat"], b["lon"]) == (1.0, 2.0) and b["address"] == "Street 1"


def test_parse_yelp():
    (b,) = parse_businesses(YELP, "cafe")
    assert b["rating"] == 3.5 and b["review_count"] == 8 and b["address"] == "MM Alam Rd, Lahore"
    assert b["socials"] == {"yelp": "https://www.yelp.com/biz/chai-corner"}
    assert "website" not in b


def test_old_single_source_key_still_works():
    c = Campaign.model_validate({"name": "x", "location": "L", "categories": ["cafe"], "source": "google_places"})
    assert c.sources == ["google_places"]
    assert Campaign(name="x", location="L", categories=["cafe"]).sources == ["overpass"]
    with pytest.raises(ValueError):
        Campaign.model_validate({"name": "x", "location": "L", "categories": ["cafe"], "sources": ["myspace"]})


def test_multi_source_discover_merges(db, campaign, monkeypatch):
    import leadscout.sources.foursquare as fsq
    import leadscout.sources.overpass as ov
    monkeypatch.setattr(ov, "geocode", lambda loc: (31.5, 74.3))
    monkeypatch.setattr(ov, "discover", lambda *a, **k: [
        {"source": "osm", "name": "Bean There", "phone": "042 1234567", "category": "cafe"}])
    monkeypatch.setattr(fsq, "discover", lambda *a, **k: parse_results(FSQ, "cafe"))
    campaign.sources = ["overpass", "foursquare"]
    lines = []
    assert pipeline.discover(db, campaign, log=lines.append) == 2  # Bean There + Old Shape Cafe
    bean = db.businesses(where="name = 'Bean There'")[0]
    assert bean["website"] == "https://beanthere.pk"  # filled in by Foursquare
    assert bean["meta"]["sources"] == ["osm", "foursquare"]
    assert "1 enriched" in lines[-1]


def test_one_failing_source_does_not_stop_the_run(db, campaign, monkeypatch):
    import leadscout.sources.overpass as ov
    monkeypatch.setattr(ov, "geocode", lambda loc: (31.5, 74.3))
    monkeypatch.setattr(ov, "discover", lambda *a, **k: [{"source": "osm", "name": "A Cafe", "phone": "0300 1111111"}])
    monkeypatch.delenv("YELP_API_KEY", raising=False)
    campaign.sources = ["overpass", "yelp"]
    lines = []
    assert pipeline.discover(db, campaign, log=lines.append) == 1
    assert any("Source yelp failed" in line for line in lines)
    campaign.sources = ["yelp"]
    with pytest.raises(RuntimeError, match="All sources failed"):
        pipeline.discover(db, campaign, log=lines.append)
