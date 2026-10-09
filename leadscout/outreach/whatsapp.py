"""WhatsApp click-to-chat links. Sending stays manual: automating personal
WhatsApp accounts breaks WhatsApp's terms and gets numbers banned."""
from __future__ import annotations

import re
from urllib.parse import quote


def normalize_phone(phone: str | None, country_code: str = "") -> str | None:
    if not phone:
        return None
    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if raw.startswith("+"):
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and country_code:
        digits = country_code + digits[1:]
    elif country_code and not digits.startswith(country_code) and len(digits) <= 10:
        digits = country_code + digits
    return digits if 8 <= len(digits) <= 15 else None


def wa_link(phone: str | None, text: str, country_code: str = "") -> str | None:
    num = normalize_phone(phone, country_code)
    return f"https://wa.me/{num}?text={quote(text)}" if num else None
