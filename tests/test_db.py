def test_dedupe_by_phone_domain_and_name(db):
    assert db.insert_business("c1", {"name": "Chai Corner", "phone": "+92 300 1234567", "address": "MM Alam"})
    assert db.insert_business("c2", {"name": "Other name", "phone": "0300-1234567"}) is None  # same phone
    assert db.insert_business("c1", {"name": "Bean", "website": "https://www.bean.pk/menu"})
    assert db.insert_business("c1", {"name": "Bean 2", "website": "bean.pk"}) is None  # same domain
    assert db.insert_business("c1", {"name": "Chai  Corner!", "address": "mm alam"}) is None  # same name+address
    assert len(db.businesses()) == 2


def test_suppression(db):
    db.suppress("Owner@Shop.pk")
    assert db.is_suppressed("owner@shop.pk")
    assert not db.is_suppressed(None, "x@y.z")


def test_shared_hosts_do_not_dedupe(db):
    assert db.insert_business("c", {"name": "A Bakery", "website": "https://facebook.com/abakery"})
    assert db.insert_business("c", {"name": "B Bakery", "website": "https://www.facebook.com/bbakery"})
