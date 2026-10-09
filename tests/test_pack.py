import csv
import zipfile
from datetime import date

import pytest

pytest.importorskip("fpdf")

from leadscout.db import now  # noqa: E402
from leadscout.export.pack import build_pack, is_free_mail, select_rows  # noqa: E402


@pytest.fixture
def leads(db, campaign):
    rows = [
        ("Chai Corner", "cafe", 80, "info@chai.pk", ["no_website", "new_business"]),
        ("Bean There", "cafe", 55, "beanthere@gmail.com", ["no_https", "not_mobile_friendly"]),
        ("Low Cafe", "cafe", 10, "low@cafe.pk", []),
        ("Bakery Ünal – Café", "bakery", 70, "hi@bakery.pk", ["no_booking"]),  # non-Latin-1 characters
        ("Gone Cafe", "cafe", 90, "gone@cafe.pk", ["no_website"]),
    ]
    for i, (name, cat, score, email, signals) in enumerate(rows):
        bid = db.insert_business(campaign.name, {"name": name, "category": cat, "phone": f"0300 00000{i}"})
        db.update_business(bid, email=email, score=score, signals=signals, status="audited", audited_at=now())
    db.suppress("gone@cafe.pk")
    return db


def test_free_mail():
    assert is_free_mail("a@gmail.com") and is_free_mail("a@yahoo.co.uk") and not is_free_mail("a@chai.pk")
    assert not is_free_mail(None)


def test_select_rows_filters(leads, campaign):
    names = [r["name"] for r in select_rows(leads, campaign, "cafe", 40)]
    assert names == ["Chai Corner", "Bean There"]  # low score and suppressed lead left out
    rows = select_rows(leads, campaign, "cafe", 40, business_emails_only=True)
    assert [r["email"] for r in rows] == ["info@chai.pk", None]


def test_build_pack(leads, campaign, tmp_path):
    path = build_pack(leads, campaign, None, 40, True, out_dir=tmp_path, today=date(2026, 10, 9))
    assert path.name == "test-all-2026-10-09.zip"
    with zipfile.ZipFile(path) as z:
        assert sorted(z.namelist()) == ["leads.csv", "report.pdf"]
        assert z.read("report.pdf").startswith(b"%PDF")
        rows = list(csv.DictReader(z.read("leads.csv").decode("utf-8-sig").splitlines()))
    assert [r["name"] for r in rows] == ["Chai Corner", "Bakery Ünal – Café", "Bean There"]
    assert "whatsapp_link" not in rows[0] and "status" not in rows[0]


def test_empty_pack_is_an_error(leads, campaign, tmp_path):
    with pytest.raises(ValueError):
        build_pack(leads, campaign, "dentist", 0, out_dir=tmp_path)
