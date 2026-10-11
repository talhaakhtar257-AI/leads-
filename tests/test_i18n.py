import pytest

from leadscout.config import Campaign
from leadscout.outreach.drafts import template_draft
from leadscout.outreach.email_sender import footer
from leadscout.outreach.followups import is_unsubscribe, strip_quoted
from leadscout.outreach.templates_i18n import MESSAGES, SIGNAL_TEXT, language_code, render
from leadscout.signals import SIGNALS, describe

BIZ = {"id": 1, "name": "Chai Corner"}


def camp(language="English", tone="friendly"):
    return Campaign(name="t", location="Lahore", categories=["cafe"], language=language, tone=tone,
                    service_pitch="PITCH", sender={"name": "Ali", "company": "WebCo"})


@pytest.mark.parametrize("code", ["ur", "roman"])
def test_every_signal_is_translated(code):
    assert set(SIGNAL_TEXT[code]) == set(SIGNALS)
    assert all(all(part.strip() for part in v) for v in SIGNAL_TEXT[code].values())
    assert set(MESSAGES[code]) == set(MESSAGES["en"])


def test_language_names():
    assert language_code("Urdu") == "ur" and language_code("اردو") == "ur"
    assert language_code("Roman Urdu") == "roman" and language_code(" english ") == "en"
    assert language_code("Spanish") is None


@pytest.mark.parametrize("language,greeting,word", [
    ("Urdu", "السلام علیکم Chai Corner ٹیم", "کوئی ویب سائٹ نہیں"),
    ("Roman Urdu", "Assalam o Alaikum Chai Corner team", "koi website nahi"),
    ("English", "Hi Chai Corner team", "no website"),
])
def test_drafts_in_each_language(language, greeting, word):
    d = template_draft(BIZ, camp(language), describe(["no_website", "no_https"]))
    assert d["email"].startswith(greeting)
    assert word in d["email"] and "PITCH" in d["email"]
    assert "{" not in "".join(d.values())  # no unfilled placeholders
    for key in ("subject", "whatsapp", "followup_1", "followup_2"):
        assert d[key].strip()


def test_every_signal_renders_in_every_language():
    for code in ("en", "ur", "roman"):
        for tone in ("friendly", "short"):
            for key in SIGNALS:
                if key == "new_business":
                    continue
                out = render(code, tone, "X", "Ali", "WebCo", "PITCH", [key, "no_https"], True)
                assert "{" not in "".join(out.values()) and "  " not in out["whatsapp"]


def test_short_tone_is_short():
    friendly = template_draft(BIZ, camp(), describe(["no_website", "no_https"]))
    short = template_draft(BIZ, camp(tone="short"), describe(["no_website", "no_https"]))
    assert len(short["email"].split()) < len(friendly["email"].split()) <= 120
    assert len(short["email"].split()) <= 50
    assert len(short["whatsapp"]) < len(friendly["whatsapp"])


def test_new_business_congratulates_in_urdu():
    d = template_draft(BIZ, camp("Urdu"), describe(["no_website", "new_business"]))
    assert "آغاز پر بہت مبارک ہو" in d["email"] and "مبارکباد" in d["whatsapp"]


def test_unknown_language_falls_back_to_english():
    d = template_draft(BIZ, camp("Spanish"), describe(["no_website"]))
    assert d["email"].startswith("Hi Chai Corner team")


def test_localized_footer_and_unsubscribe():
    assert "dobara rabta nahi hoga" in footer(camp("Roman Urdu"))
    assert "دوبارہ رابطہ نہیں ہوگا" in footer(camp("Urdu"))
    assert is_unsubscribe("bhai mat bhejo")
    quoted = "Ji zaroor bhejein\n\n" + footer(camp("Roman Urdu"))
    assert strip_quoted(quoted) == "Ji zaroor bhejein"
