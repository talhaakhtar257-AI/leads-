from datetime import date

from leadscout.audit.website import analyze_html, audit_business
from leadscout.enrich.contacts import best_email, extract_contacts

TODAY = date(2026, 10, 9)


def test_old_site_signals(fixture_text):
    signals, details = analyze_html(fixture_text("old_site.html"), "http://beanthere.pk/", TODAY)
    assert {"no_https", "not_mobile_friendly", "outdated_copyright", "no_booking", "missing_seo_basics"} <= set(signals)
    assert details["copyright_year"] == 2016


def test_modern_site_is_clean(fixture_text):
    signals, details = analyze_html(fixture_text("modern_site.html"), "https://smile.example/", TODAY)
    assert signals == []
    assert details["copyright_year"] == 2026


def test_extract_contacts(fixture_text):
    c = extract_contacts(fixture_text("old_site.html"), "http://beanthere.pk/")
    assert c["emails"] == ["hello@beanthere.pk", "info@beanthere.pk"]  # logo@2x.png filtered
    assert c["phones"] == ["+92421234567"]
    assert c["socials"]["facebook"] == "https://www.facebook.com/beantherepk"  # sharer link ignored
    assert c["contact_links"] == ["http://beanthere.pk/contact-us"]
    assert best_email(c["emails"], "beanthere.pk") == "info@beanthere.pk"


def test_best_email_prefers_own_domain():
    assert best_email(["owner@gmail.com", "sales@shop.pk"], "shop.pk") == "sales@shop.pk"
    assert best_email([], "shop.pk") is None


def test_no_website_and_social_only_need_no_network():
    r = audit_business({"name": "A", "website": None, "phone": "123", "rating": 3.5, "review_count": 4})
    assert set(r["signals"]) == {"no_website", "low_rating", "few_reviews"}
    r = audit_business({"name": "B", "website": "https://www.facebook.com/bcafe", "phone": None})
    assert "social_only" in r["signals"]
    assert r["socials"]["facebook"] == "https://www.facebook.com/bcafe"
