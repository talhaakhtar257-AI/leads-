"""Read and update the .env file from the dashboard, keeping comments and unknown keys."""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


@dataclass(frozen=True)
class KeySpec:
    name: str
    label: str
    group: str
    help: str
    link: str = ""
    secret: bool = True
    cost: str = "free"  # free | free-tier | paid
    default: str = ""


KEYS: list[KeySpec] = [
    KeySpec("GEMINI_API_KEY", "Google Gemini key", "AI message writer",
            "Writes better, personalized messages in any language (Urdu included). Free tier.",
            "https://aistudio.google.com/apikey", cost="free-tier"),
    KeySpec("GROQ_API_KEY", "Groq key", "AI message writer",
            "Fast free alternative to Gemini.", "https://console.groq.com/keys", cost="free-tier"),
    KeySpec("OLLAMA_MODEL", "Ollama model (runs on your computer)", "AI message writer",
            "Free and offline if you install Ollama, e.g. llama3.1.", "https://ollama.com", secret=False),
    KeySpec("ANTHROPIC_API_KEY", "Claude key", "AI message writer",
            "Paid. Only used if you choose Claude in Settings.", "https://console.anthropic.com", cost="paid"),
    KeySpec("SMTP_USER", "Gmail address", "Sending email",
            "The Gmail account LeadScout sends from.", secret=False, cost=""),
    KeySpec("SMTP_PASSWORD", "Gmail app password", "Sending email",
            "Not your normal password: turn on 2-step verification, then create an app password.",
            "https://myaccount.google.com/apppasswords", cost=""),
    KeySpec("SMTP_HOST", "Mail server", "Sending email", "Leave as is for Gmail.", secret=False,
            default="smtp.gmail.com", cost=""),
    KeySpec("SMTP_PORT", "Mail server port", "Sending email", "Leave as is for Gmail.", secret=False, default="587", cost=""),
    KeySpec("IMAP_HOST", "Inbox server (reply checking)", "Sending email", "Leave as is for Gmail.", secret=False,
            default="imap.gmail.com", cost=""),
    KeySpec("FOURSQUARE_API_KEY", "Foursquare service key", "Extra business sources",
            "Adds phones and websites. Free monthly allowance.", "https://foursquare.com/developers/",
            cost="free-tier"),
    KeySpec("GOOGLE_PLACES_API_KEY", "Google Places key", "Extra business sources",
            "Adds ratings and reviews. Free monthly quota, but Google asks for a card.",
            "https://console.cloud.google.com/google/maps-apis", cost="free-tier"),
    KeySpec("PAGESPEED_API_KEY", "PageSpeed key", "Extra business sources",
            "Measures website speed. Free.", "https://developers.google.com/speed/docs/insights/v5/get-started"),
    KeySpec("YELP_API_KEY", "Yelp key", "Extra business sources",
            "Paid after a short trial. Not needed.", "https://www.yelp.com/developers", cost="paid"),
    KeySpec("HUBSPOT_TOKEN", "HubSpot token", "Exports", "Push leads to the free HubSpot CRM.",
            "https://developers.hubspot.com/docs/api/private-apps", cost="free"),
    KeySpec("GOOGLE_SERVICE_ACCOUNT_FILE", "Google service-account file path", "Exports",
            "Path to the JSON key file, for Google Sheets export.", secret=False, cost=""),
]
KEY_NAMES = {k.name for k in KEYS}


def _unquote(v: str) -> str:
    v = v.strip()
    if v.startswith("#"):  # "KEY=   # comment" means an empty value
        return ""
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v.split(" #")[0].strip() if " #" in v else v


def read_env(path: str | Path) -> dict[str, str]:
    p = Path(path)
    values: dict[str, str] = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = LINE_RE.match(line)
            if m and not line.lstrip().startswith("#"):
                values[m.group(1)] = _unquote(m.group(2))
    return values


def _format(value: str) -> str:
    return f'"{value}"' if re.search(r"[\s#'\"]", value) else value


def update_env(path: str | Path, changes: dict[str, str | None]) -> None:
    """Set (str) or remove (None) keys, keeping every other line as it was. Writes atomically."""
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    pending = dict(changes)
    out: list[str] = []
    for line in lines:
        m = LINE_RE.match(line)
        if m and not line.lstrip().startswith("#") and m.group(1) in pending:
            key = m.group(1)
            value = pending.pop(key)
            if value is None:
                out.append(f"{key}=")
            else:
                comment = ""
                tail = m.group(2)
                if " #" in tail and not tail.strip().startswith(('"', "'")):
                    comment = "  #" + tail.split(" #", 1)[1]
                out.append(f"{key}={_format(value)}{comment}")
            continue
        out.append(line)
    for key, value in pending.items():
        if value is not None:
            out.append(f"{key}={_format(value)}")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".env.", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, p)
    for key, value in changes.items():  # apply now, no restart needed
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


def mask(value: str) -> str:
    if not value:
        return ""
    return "••••" + value[-4:] if len(value) > 8 else "••••"


def test_smtp_login(host: str, port: int, user: str, password: str) -> str | None:
    """Log in and out without sending anything. Returns None on success, else a readable error."""
    import smtplib
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, password)
    except smtplib.SMTPAuthenticationError:
        return "The email or app password was not accepted. For Gmail, use an app password, not your normal password."
    except (OSError, smtplib.SMTPException) as e:
        return f"Could not reach the mail server: {e}"
    return None
