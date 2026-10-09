from leadscout.sources.google_places import parse_places
from leadscout.sources.overpass import build_query, parse_elements, tag_filters


def test_parse_overpass(fixture_json):
    out = parse_elements(fixture_json("overpass.json"), "cafe")
    assert [b["name"] for b in out] == ["Chai Corner", "Bean There"]  # nameless element dropped
    chai, bean = out
    assert chai["phone"] == "0300 1234567"
    assert chai["address"] == "MM Alam Road, Lahore"
    assert chai["website"] is None
    assert bean["lat"] == 31.52  # way uses its center
    assert bean["socials"] == {"instagram": "https://instagram.com/beanthere"}


def test_tag_filters_and_query():
    assert tag_filters("shop=tailor") == ['"shop"="tailor"']
    q = build_query("salon", 1.0, 2.0, 500)
    assert '"shop"="hairdresser"' in q and "around:500,1.0,2.0" in q


def test_parse_places():
    data = {"places": [
        {"id": "a", "displayName": {"text": "Open Cafe"}, "rating": 3.6, "userRatingCount": 12,
         "businessStatus": "OPERATIONAL", "websiteUri": "https://open.example"},
        {"id": "b", "displayName": {"text": "Closed Cafe"}, "businessStatus": "CLOSED_PERMANENTLY"},
    ]}
    out = parse_places(data, "cafe")
    assert len(out) == 1 and out[0]["rating"] == 3.6 and out[0]["review_count"] == 12
