"""Extract emails, phone numbers and social links from web pages."""
from __future__ import annotations

import re
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
JUNK_EMAIL_PARTS = ("example.", "sentry", "wixpress", "domain.com", "yourdomain", "email.com", "@2x", "godaddy")
JUNK_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")

SOCIAL_PATTERNS = {
    "facebook": re.compile(r"https?://(?:www\.|m\.)?facebook\.com/[^\s\"'<>]+", re.I),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[^\s\"'<>]+", re.I),
    "linkedin": re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/[^\s\"'<>]+", re.I),
    "tiktok": re.compile(r"https?://(?:www\.)?tiktok\.com/@[^\s\"'<>]+", re.I),
    "youtube": re.compile(r"https?://(?:www\.)?youtube\.com/[^\s\"'<>]+", re.I),
    "whatsapp": re.compile(r"https?://(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com)/[^\s\"'<>]+", re.I),
}
IGNORED_SOCIAL_PATHS = ("sharer", "share.php", "/plugins/", "/tr?", "/dialog/", "intent/")

CONTACT_PATHS = ("contact", "contact-us", "about", "about-us")


def clean_email(e: str) -> str | None:
    e = unquote(e).strip().strip(".").lower()
    if not EMAIL_RE.fullmatch(e):
        return None
    if any(p in e for p in JUNK_EMAIL_PARTS) or e.endswith(JUNK_EMAIL_SUFFIXES):
        return None
    return e


def extract_contacts(html: str, base_url: str = "") -> dict:
    soup = BeautifulSoup(html, "html.parser")
    emails: set[str] = set()
    phones: set[str] = set()
    socials: dict[str, str] = {}
    contact_links: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if low.startswith("mailto:"):
            e = clean_email(href[7:].split("?")[0])
            if e:
                emails.add(e)
        elif low.startswith("tel:"):
            num = re.sub(r"[^\d+]", "", href[4:])
            if len(re.sub(r"\D", "", num)) >= 7:
                phones.add(num)
        elif base_url and any(p in low.rstrip("/").rsplit("/", 1)[-1] for p in CONTACT_PATHS):
            contact_links.add(urljoin(base_url, href))

    text = soup.get_text(" ")
    for e in EMAIL_RE.findall(text):
        ce = clean_email(e)
        if ce:
            emails.add(ce)

    for name, pat in SOCIAL_PATTERNS.items():
        for m in pat.findall(html):
            url = m.rstrip("/\\")
            if any(x in url.lower() for x in IGNORED_SOCIAL_PATHS):
                continue
            socials.setdefault(name, url)
            break

    return {
        "emails": sorted(emails),
        "phones": sorted(phones),
        "socials": socials,
        "contact_links": sorted(contact_links)[:3],
    }


def best_email(emails: list[str], domain: str | None) -> str | None:
    """Prefer an address on the business's own domain, then generic inboxes."""
    if not emails:
        return None
    if domain:
        own = [e for e in emails if e.endswith("@" + domain) or e.endswith("." + domain)]
        if own:
            emails = own
    for prefix in ("info@", "contact@", "hello@", "booking", "reservations@", "office@"):
        for e in emails:
            if e.startswith(prefix):
                return e
    return emails[0]
