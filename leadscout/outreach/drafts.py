"""Draft personalized outreach that cites real audit findings (never invented ones)."""
from __future__ import annotations

from typing import Any

from ..config import Campaign
from ..llm.base import LLM, LLMError, parse_json
from ..scoring import relevant_signals
from ..signals import describe

SYSTEM = """You write short, friendly, non-spammy cold outreach for a local service provider.
Rules:
- Only mention problems listed under FINDINGS. Never invent facts, numbers, reviews or compliments.
- Lead with one concrete finding and why it costs the business customers, then offer help.
- Sound like a real local person, not a marketer. No hype words, no ALL CAPS, no emojis in email.
- Email body: 60-110 words, plain text, end with a soft question (e.g. "Want me to send the 1-page audit?").
- WhatsApp: 2-4 short sentences, warm and casual; one emoji max.
- Follow-ups: 1-3 sentences each, polite bump that adds one small extra value.
- Do not include a signature, unsubscribe line or address; those are added automatically.
- If FINDINGS include "Recently opened", start with a short, genuine congratulations on the opening.
- Write everything in the requested LANGUAGE.
Reply with only a JSON object with keys: reason, subject, email, whatsapp, followup_1, followup_2.
"reason" is 1-2 sentences in English for the salesperson explaining why this is a good lead."""


def build_prompt(biz: dict[str, Any], campaign: Campaign, findings: list[dict[str, str]]) -> str:
    lines = [
        f"LANGUAGE: {campaign.language}",
        f"MY SERVICE: {campaign.service_pitch}",
        f"MY NAME: {campaign.sender.name} from {campaign.sender.company}",
        "",
        f"BUSINESS: {biz['name']} ({(biz.get('category') or '').replace('_', ' ')})",
        f"ADDRESS: {biz.get('address') or 'unknown'}",
        f"WEBSITE: {biz.get('website') or 'none'}",
    ]
    if biz.get("rating") is not None:
        lines.append(f"GOOGLE RATING: {biz['rating']} from {biz.get('review_count') or 0} reviews")
    lines.append("FINDINGS:")
    for f in findings:
        lines.append(f"- {f['title']}: {f['impact']} Fix: {f['fix']}")
    return "\n".join(lines)


def template_reason(findings: list[dict[str, str]], service: str) -> str:
    if not findings:
        return "No strong problem signals found for this service."
    titles = "; ".join(f["title"] for f in findings)
    return f"{titles}. Good fit for {service.replace('_', ' ')}."


def _lc(text: str) -> str:
    """Lower-case only the first letter so acronyms like HTTPS/SEO survive mid-sentence."""
    return text[:1].lower() + text[1:]


def template_draft(biz: dict[str, Any], campaign: Campaign, findings: list[dict[str, str]]) -> dict[str, str]:
    """Free, no-LLM fallback (English)."""
    s = campaign.sender
    is_new = any(f["key"] == "new_business" for f in findings)
    findings = [f for f in findings if f["key"] != "new_business"]
    first = findings[0] if findings else {"title": "a few quick wins online", "impact": "", "fix": campaign.service_pitch}
    extra = f" I also noticed: {_lc(findings[1]['title'])}." if len(findings) > 1 else ""
    email = (
        f"Hi {biz['name']} team,\n\n"
        + (f"Congratulations on opening {biz['name']}! " if is_new else "")
        + f"I'm {s.name}, I work with local businesses nearby. While looking you up I noticed: {_lc(first['title'])}. "
        f"{first['impact']}{extra}\n\n"
        f"{first['fix']} {campaign.service_pitch}\n\n"
        "I put together a free 1-page audit for you. Want me to send it over?"
    )
    whatsapp = (
        f"Hi! {'Congrats on the new opening! ' if is_new else ''}I'm {s.name} from {s.company}. I came across {biz['name']} and noticed: {_lc(first['title'])}. "
        f"I made a quick free audit with simple fixes. Can I send it here? 🙂"
    )
    return {
        "reason": template_reason(findings, campaign.service),
        "subject": f"Quick idea for {biz['name']}",
        "email": email,
        "whatsapp": whatsapp,
        "followup_1": f"Hi again, just bumping this in case it got buried. Happy to send the free audit for {biz['name']}, no strings attached.",
        "followup_2": "Last note from me. If improving this isn't a priority right now, no problem at all. I'll leave the offer open.",
    }


def draft_for(biz: dict[str, Any], campaign: Campaign, llm: LLM | None) -> dict[str, str]:
    findings = describe(relevant_signals(biz.get("signals") or [], campaign.service, top=3))
    if llm is not None:
        try:
            out = parse_json(llm.generate(SYSTEM, build_prompt(biz, campaign, findings)))
            required = ("subject", "email", "whatsapp", "followup_1", "followup_2")
            if all(isinstance(out.get(k), str) and out[k].strip() for k in required):
                out.setdefault("reason", template_reason(findings, campaign.service))
                return out
        except (LLMError, ValueError):
            pass  # fall back to the template so a run never fails on one bad LLM reply
    return template_draft(biz, campaign, findings)
