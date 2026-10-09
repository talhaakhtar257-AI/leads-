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


def test_merge_fills_gaps_and_tracks_sources(db):
    bid, how = db.upsert_business("c", {"name": "Chai Corner", "phone": "0300 1234567", "source": "osm"})
    assert how == "new"
    db.update_business(bid, audited_at="2026-01-01")
    bid2, how = db.upsert_business("c", {"name": "Chai Corner Cafe", "phone": "+92 300 1234567", "source": "foursquare",
                                         "website": "https://chai.pk", "rating": 4.1, "socials": {"instagram": "x"}})
    assert (bid2, how) == (bid, "merged")
    b = db.business(bid)
    assert b["name"] == "Chai Corner"  # existing values are kept
    assert b["website"] == "https://chai.pk" and b["domain"] == "chai.pk" and b["rating"] == 4.1
    assert b["socials"] == {"instagram": "x"}
    assert b["meta"]["sources"] == ["osm", "foursquare"]
    assert b["audited_at"] is None  # new website -> re-audit
    assert db.upsert_business("c", {"name": "Chai Corner", "phone": "0300 1234567", "source": "osm"}) == (bid, "duplicate")


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    from leadscout.db import DB
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE businesses (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign TEXT NOT NULL, source TEXT,"
                " source_id TEXT, name TEXT NOT NULL, category TEXT, address TEXT, phone TEXT, website TEXT, domain TEXT,"
                " email TEXT, lat REAL, lon REAL, rating REAL, review_count INTEGER, opening_hours TEXT,"
                " socials TEXT DEFAULT '{}', signals TEXT DEFAULT '[]', audit TEXT DEFAULT '{}', score INTEGER,"
                " reason TEXT, status TEXT DEFAULT 'new', phone_key TEXT, name_key TEXT, created_at TEXT, audited_at TEXT)")
    con.execute("INSERT INTO businesses (campaign, name) VALUES ('c', 'Old Lead')")
    con.commit()
    con.close()
    db = DB(path)
    assert db.businesses()[0]["meta"] == {}
    assert db.insert_business("c", {"name": "New Lead", "meta": {"osm_version": 1}})
