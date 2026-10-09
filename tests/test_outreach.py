from leadscout.db import now
from leadscout.llm.base import LLMError, parse_json
from leadscout.outreach import email_sender
from leadscout.outreach.drafts import build_prompt, draft_for
from leadscout.outreach.followups import is_unsubscribe, record_reply
from leadscout.outreach.whatsapp import normalize_phone, wa_link
from leadscout import pipeline


class FakeLLM:
    name = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def generate(self, system, prompt, max_tokens=1500):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


BIZ = {"id": 1, "name": "Chai Corner", "category": "cafe", "signals": ["no_website", "few_reviews"],
       "email": "info@chai.pk", "phone": "03001234567"}


def test_normalize_phone():
    assert normalize_phone("0300 1234567", "92") == "923001234567"
    assert normalize_phone("+1 (415) 555-0100") == "14155550100"
    assert normalize_phone("0092 300 1234567") == "923001234567"
    assert normalize_phone("123") is None
    link = wa_link("0300 1234567", "Hi there!", "92")
    assert link == "https://wa.me/923001234567?text=Hi%20there%21"


def test_prompt_only_contains_relevant_findings(campaign):
    from leadscout.signals import describe
    p = build_prompt(BIZ, campaign, describe(["no_website"]))
    assert "No website" in p and "Few Google reviews" not in p


def test_llm_draft_used_when_valid(campaign):
    llm = FakeLLM('```json\n{"reason":"r","subject":"S","email":"E","whatsapp":"W","followup_1":"F1","followup_2":"F2"}\n```')
    d = draft_for(BIZ, campaign, llm)
    assert d["subject"] == "S" and d["whatsapp"] == "W"
    assert "No website" in llm.prompts[0]


def test_falls_back_to_template(campaign):
    for llm in (FakeLLM(LLMError("down")), FakeLLM("not json"), FakeLLM('{"subject": "only"}'), None):
        d = draft_for(BIZ, campaign, llm)
        assert "no website" in d["email"].lower()
        assert d["subject"] == "Quick idea for Chai Corner"


def test_parse_json():
    assert parse_json('Sure! {"a": 1} hope that helps') == {"a": 1}


def test_unsubscribe_detection():
    assert is_unsubscribe("Please unsubscribe me")
    assert is_unsubscribe("STOP")
    assert not is_unsubscribe("Can you stop by the shop on Monday?")


def _seed(db, campaign):
    bid = db.insert_business(campaign.name, {"name": "Chai Corner", "phone": "03001234567"})
    db.update_business(bid, email="info@chai.pk", signals=["no_website"], score=60, status="audited", audited_at=now())
    pipeline.draft(db, campaign, log=lambda *_: None)
    return bid


def test_draft_send_followup_flow(db, campaign, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    campaign.llm = "template"
    bid = _seed(db, campaign)
    msgs = db.messages("m.business_id = ?", (bid,))
    assert sorted((m["channel"], m["step"]) for m in msgs) == [("email", 0), ("email", 1), ("email", 2), ("whatsapp", 0)]
    assert list((tmp_path / "output" / "audits").glob("*.html"))

    # Nothing goes out before review.
    assert email_sender.due_messages(db, campaign) == []
    db.conn.execute("UPDATE messages SET status = 'approved' WHERE channel = 'email'")
    db.conn.commit()

    sent_msgs = []

    class FakeSMTP:
        def __init__(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def send(self, msg): sent_msgs.append(msg)

    monkeypatch.setattr(email_sender, "SMTPSender", FakeSMTP)
    n = email_sender.send_due(db, campaign, log=lambda *_: None, sleep=lambda s: None)
    assert n == 1
    msg = sent_msgs[0]
    assert msg["To"] == "info@chai.pk" and "unsubscribe" in msg["List-Unsubscribe"]
    assert campaign.sender.address in msg.get_content()
    assert db.business(bid)["status"] == "contacted"
    followups = db.messages("m.business_id = ? AND m.step > 0", (bid,))
    assert all(f["status"] == "scheduled" and f["scheduled_at"] > now() for f in followups)

    # A reply cancels follow-ups; an unsubscribe also suppresses the address.
    assert record_reply(db, bid, "info@chai.pk", "Please unsubscribe") == "unsubscribed"
    assert db.is_suppressed("info@chai.pk")
    assert all(f["status"] == "cancelled" for f in db.messages("m.business_id = ? AND m.step > 0", (bid,)))


def test_daily_cap(db, campaign, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    campaign.llm = "template"
    campaign.limits.daily_emails = 0
    _seed(db, campaign)
    db.conn.execute("UPDATE messages SET status = 'approved'")
    db.conn.commit()
    assert email_sender.send_due(db, campaign, log=lambda *_: None) == 0
