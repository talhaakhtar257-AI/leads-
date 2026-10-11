"""Built-in message templates in English, Urdu and Roman Urdu: good outreach with no AI key at all.

The Urdu wording avoids gendered verb endings (کرتا/کرتی) so it reads right whoever sends it.
"""
from __future__ import annotations

from ..signals import SIGNALS

LANGUAGE_CODES = {
    "english": "en", "en": "en",
    "urdu": "ur", "ur": "ur", "اردو": "ur",
    "roman urdu": "roman", "roman-urdu": "roman", "romanurdu": "roman", "roman": "roman",
}
LANGUAGE_NAMES = {"en": "English", "ur": "Urdu (اردو)", "roman": "Roman Urdu"}


def language_code(language: str | None) -> str | None:
    """Template language for a campaign language, or None if there is no built-in template for it."""
    return LANGUAGE_CODES.get((language or "english").strip().lower())


# signal -> (title, impact, fix)
SIGNAL_TEXT: dict[str, dict[str, tuple[str, str, str]]] = {
    "en": {k: (s.title, s.impact, s.fix) for k, s in SIGNALS.items()},
    "ur": {
        "new_business": ("حال ہی میں کھلا کاروبار",
                         "نئے کاروبار کے پہلے چند مہینے طے کرتے ہیں کہ لوگ انہیں آن لائن ڈھونڈ پاتے ہیں یا نہیں۔",
                         "لانچ پیکج: ویب سائٹ، گوگل بزنس پروفائل اور پہلے ریویوز۔"),
        "no_website": ("کوئی ویب سائٹ نہیں",
                       "گاہک آن لائن آپ کا مینیو، سروسز، قیمتیں یا اوقات نہیں دیکھ پاتے، اس لیے کسی اور کے پاس چلے جاتے ہیں۔",
                       "ایک تیز اور سادہ ویب سائٹ جس میں آپ کی سروسز، نقشہ، اوقات اور کال / واٹس ایپ بٹن ہو۔"),
        "social_only": ("ویب سائٹ کی جگہ صرف فیس بک/انسٹاگرام پیج",
                        "سوشل پیجز گوگل پر کم نظر آتے ہیں اور ان پر آپ کا پورا کنٹرول نہیں ہوتا۔",
                        "آپ کے اپنے ڈومین پر ویب سائٹ جو سوشل پیجز سے جڑی ہو۔"),
        "free_subdomain": ("مفت سب ڈومین پر ویب سائٹ",
                           "name.wixsite.com جیسے پتے کم قابلِ اعتماد لگتے ہیں اور یاد رکھنا مشکل ہوتا ہے۔",
                           "اپنا ڈومین، مثلاً yourbusiness.com۔"),
        "site_down": ("ویب سائٹ بند ہے یا ایرر دیتی ہے",
                      "گوگل یا میپس سے آنے والے لوگ ایرر دیکھ کر واپس چلے جاتے ہیں۔",
                      "ہوسٹنگ اور ڈومین ٹھیک کرنا اور نگرانی لگانا۔"),
        "no_https": ("ویب سائٹ محفوظ (HTTPS) نہیں",
                     "براؤزر 'Not secure' کی وارننگ دکھاتا ہے جس سے لوگ گھبرا کر چلے جاتے ہیں، اور گوگل رینکنگ بھی کم ہوتی ہے۔",
                     "مفت SSL سرٹیفکیٹ لگا کر پوری سائٹ HTTPS پر کرنا۔"),
        "not_mobile_friendly": ("موبائل پر ٹھیک نہیں کھلتی",
                                "زیادہ تر لوگ فون پر سرچ کرتے ہیں؛ موبائل پر خراب سائٹ گاہک کھو دیتی ہے۔",
                                "ایسا ڈیزائن جو ہر اسکرین پر اچھا چلے۔"),
        "slow_site": ("ویب سائٹ سست ہے",
                      "سست صفحے کھلنے سے پہلے ہی لوگ چلے جاتے ہیں اور گوگل پر بھی نیچے آتے ہیں۔",
                      "تصاویر چھوٹی کرنا اور سائٹ کو ہلکا بنانا تاکہ 2 سے 3 سیکنڈ میں کھلے۔"),
        "outdated_copyright": ("ویب سائٹ پرانی لگتی ہے",
                               "فوٹر میں پرانا سال دیکھ کر لگتا ہے کہ سائٹ پر کوئی توجہ نہیں دیتا۔",
                               "ڈیزائن اور معلومات کو تازہ کرنا۔"),
        "no_contact_form": ("رابطہ فارم نہیں",
                            "جو لوگ کال نہیں کرنا چاہتے ان کے پاس آپ تک پہنچنے کا آسان راستہ نہیں۔",
                            "ایک انکوائری فارم جو سیدھا آپ کی ای میل یا واٹس ایپ پر آئے۔"),
        "no_booking": ("آن لائن بکنگ یا آرڈر نہیں",
                       "گاہک چوبیس گھنٹے آن لائن بک یا آرڈر کرنا چاہتے ہیں؛ یہ سہولت نہ ہو تو وہ دوسروں کے پاس جاتے ہیں۔",
                       "آن لائن بکنگ، ریزرویشن یا آرڈر کی سہولت۔"),
        "no_social_links": ("سوشل میڈیا کے لنکس نہیں",
                            "لوگ آپ کو فالو نہیں کر پاتے اور تازہ تصاویر یا ریویوز نہیں دیکھ پاتے۔",
                            "سوشل پروفائلز کو ویب سائٹ سے جوڑنا۔"),
        "missing_seo_basics": ("بنیادی SEO نہیں (ٹائٹل/تفصیل)",
                               "گوگل آپ کی سائٹ کا اچھا خلاصہ نہیں دکھاتا، اس لیے کم لوگ کلک کرتے ہیں۔",
                               "درست ٹائٹل، تفصیل اور لوکل SEO سیٹ اپ۔"),
        "low_rating": ("گوگل ریٹنگ کم ہے",
                       "4.0 سے کم ریٹنگ دیکھ کر بہت سے لوگ میپس پر آپ کو چھوڑ دیتے ہیں۔",
                       "ریویوز جمع کرنے اور ان کا جواب دینے کا نظام۔"),
        "few_reviews": ("گوگل ریویوز بہت کم ہیں",
                        "کم ریویوز والے کاروبار آس پاس کے حریفوں سے کم قابلِ اعتماد لگتے ہیں۔",
                        "ہر وزٹ کے بعد خودکار ریویو کی درخواست (واٹس ایپ یا QR کوڈ)۔"),
        "no_email_found": ("کوئی ای میل ایڈریس نہیں",
                           "گاہک اور پارٹنرز آپ سے تحریری رابطہ آسانی سے نہیں کر پاتے۔",
                           "اپنے ڈومین پر پروفیشنل ای میل۔"),
    },
    "roman": {
        "new_business": ("Naya khula karobar",
                         "Naye karobar ke pehle chand mahine tay karte hain ke log unhein online dhoond paate hain ya nahi.",
                         "Launch package: website, Google Business Profile aur pehle reviews."),
        "no_website": ("Koi website nahi",
                       "Customers online aap ka menu, services, qeemat ya timings nahi dekh paate, is liye kisi aur ke paas chale jaate hain.",
                       "Ek tez aur saada website jis mein aap ki services, map, timings aur call / WhatsApp button ho."),
        "social_only": ("Website ki jagah sirf Facebook/Instagram page",
                        "Social pages Google par kam nazar aate hain aur un par aap ka poora control nahi hota.",
                        "Aap ke apne domain par website jo social pages se juri ho."),
        "free_subdomain": ("Free subdomain par website",
                           "name.wixsite.com jaise address kam bharosemand lagte hain aur yaad rakhna mushkil hota hai.",
                           "Apna domain, maslan yourbusiness.com."),
        "site_down": ("Website band hai ya error deti hai",
                      "Google ya Maps se aane wale log error dekh kar wapas chale jaate hain.",
                      "Hosting aur domain theek karna aur nigrani lagana."),
        "no_https": ("Website secure (HTTPS) nahi",
                     "Browser 'Not secure' ki warning dikhata hai jis se log ghabra kar chale jaate hain, aur Google ranking bhi kam hoti hai.",
                     "Free SSL certificate laga kar poori site HTTPS par karna."),
        "not_mobile_friendly": ("Mobile par theek nahi khulti",
                                "Zyada tar log phone par search karte hain; mobile par kharab site customer kho deti hai.",
                                "Aisa design jo har screen par acha chale."),
        "slow_site": ("Website slow hai",
                      "Slow pages khulne se pehle hi log chale jaate hain aur Google par bhi neeche aate hain.",
                      "Tasveerein chhoti karna aur site ko halka banana taake 2 se 3 second mein khule."),
        "outdated_copyright": ("Website purani lagti hai",
                               "Footer mein purana saal dekh kar lagta hai ke site par koi tawajjo nahi deta.",
                               "Design aur maloomat ko taaza karna."),
        "no_contact_form": ("Contact form nahi",
                            "Jo log call nahi karna chahte un ke paas aap tak pohanchne ka aasan rasta nahi.",
                            "Ek inquiry form jo seedha aap ki email ya WhatsApp par aaye."),
        "no_booking": ("Online booking ya order nahi",
                       "Customers chaubees ghante online book ya order karna chahte hain; yeh sahulat na ho to woh doosron ke paas jaate hain.",
                       "Online booking, reservation ya order ki sahulat."),
        "no_social_links": ("Social media links nahi",
                            "Log aap ko follow nahi kar paate aur taaza tasveerein ya reviews nahi dekh paate.",
                            "Social profiles ko website se jorna."),
        "missing_seo_basics": ("Basic SEO nahi (title/description)",
                               "Google aap ki site ka acha khulasa nahi dikhata, is liye kam log click karte hain.",
                               "Durust title, description aur local SEO setup."),
        "low_rating": ("Google rating kam hai",
                       "4.0 se kam rating dekh kar bohat se log Maps par aap ko chhor dete hain.",
                       "Reviews jama karne aur un ka jawab dene ka nizam."),
        "few_reviews": ("Google reviews bohat kam hain",
                        "Kam reviews wale karobar aas paas ke competitors se kam bharosemand lagte hain.",
                        "Har visit ke baad khud-ba-khud review ki request (WhatsApp ya QR code)."),
        "no_email_found": ("Koi email address nahi",
                           "Customers aur partners aap se likh kar aasani se rabta nahi kar paate.",
                           "Apne domain par professional email."),
    },
}

GENERIC_PROBLEM = {
    "en": "a few quick wins online",
    "ur": "آن لائن چند فوری بہتریاں",
    "roman": "online kuch fauri behtariyan",
}

# Placeholders: {name} business, {me} sender name, {company}, {problem}, {problem2}, {impact}, {fix}, {pitch},
# {congrats} / {congrats_short} (empty unless the business opened recently), {extra} (second problem or empty).
MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "subject": "Quick idea for {name}",
        "congrats": "Congratulations on opening {name}! ",
        "congrats_short": "Congrats on the new opening! ",
        "extra": " I also noticed: {problem2}.",
        "email_friendly": (
            "Hi {name} team,\n\n{congrats}I'm {me}, I work with local businesses nearby. "
            "While looking you up I noticed: {problem}. {impact}{extra}\n\n{fix} {pitch}\n\n"
            "I put together a free 1-page audit for you. Want me to send it over?"
        ),
        "email_short": "Hi {name} team,\n\n{congrats}I noticed: {problem}. {impact}\n\n{pitch} Want a free 1-page audit?",
        "whatsapp_friendly": (
            "Hi! {congrats_short}I'm {me} from {company}. I came across {name} and noticed: {problem}. "
            "I made a quick free audit with simple fixes. Can I send it here? 🙂"
        ),
        "whatsapp_short": "Hi! {congrats_short}{name}: {problem}. Want a quick free audit? 🙂",
        "followup_1": "Hi again, just bumping this in case it got buried. Happy to send the free audit for {name}, no strings attached.",
        "followup_2": "Last note from me. If improving this isn't a priority right now, no problem at all. I'll leave the offer open.",
        "footer_unsubscribe": 'Not interested? Reply "unsubscribe" and I won\'t contact you again.',
    },
    "ur": {
        "subject": "{name} کے لیے ایک فوری تجویز",
        "congrats": "{name} کے آغاز پر بہت مبارک ہو! ",
        "congrats_short": "نئے آغاز کی مبارکباد! ",
        "extra": " اس کے علاوہ: {problem2}۔",
        "email_friendly": (
            "السلام علیکم {name} ٹیم،\n\n{congrats}میرا نام {me} ہے اور میرا کام مقامی کاروباروں کی آن لائن موجودگی بہتر بنانا ہے۔ "
            "آپ کے بارے میں دیکھتے ہوئے یہ نظر آیا: {problem}۔ {impact}{extra}\n\n{fix} {pitch}\n\n"
            "میں نے آپ کے لیے ایک صفحے کا مفت جائزہ تیار کیا ہے۔ کیا میں آپ کو بھیج دوں؟"
        ),
        "email_short": "السلام علیکم {name} ٹیم،\n\n{congrats}یہ نظر آیا: {problem}۔ {impact}\n\n{pitch} کیا ایک صفحے کا مفت جائزہ بھیج دوں؟",
        "whatsapp_friendly": (
            "السلام علیکم! {congrats_short}میں {me} ہوں، {company} سے۔ {name} کے بارے میں دیکھا تو یہ نظر آیا: {problem}۔ "
            "میں نے آسان حل کے ساتھ ایک مفت جائزہ بنایا ہے۔ کیا یہاں بھیج دوں؟ 🙂"
        ),
        "whatsapp_short": "السلام علیکم! {congrats_short}{name}: {problem}۔ مفت جائزہ بھیج دوں؟ 🙂",
        "followup_1": "دوبارہ سلام، شاید میرا پیغام دب گیا ہو۔ {name} کے لیے مفت جائزہ بھیجنے میں خوشی ہوگی، کوئی شرط نہیں۔",
        "followup_2": "یہ میری آخری یاد دہانی ہے۔ اگر ابھی یہ ترجیح نہیں تو کوئی بات نہیں، پیشکش برقرار رہے گی۔",
        "footer_unsubscribe": 'دلچسپی نہیں؟ "unsubscribe" لکھ کر جواب دیں، دوبارہ رابطہ نہیں ہوگا۔',
    },
    "roman": {
        "subject": "{name} ke liye ek fauri idea",
        "congrats": "{name} ke aaghaz par bohat mubarak ho! ",
        "congrats_short": "Naye aaghaz ki mubarakbaad! ",
        "extra": " Is ke ilawa: {problem2}.",
        "email_friendly": (
            "Assalam o Alaikum {name} team,\n\n{congrats}Mera naam {me} hai aur mera kaam local karobaron ki online "
            "maujoodgi behtar banana hai. Aap ke baare mein dekhte hue yeh nazar aaya: {problem}. {impact}{extra}\n\n"
            "{fix} {pitch}\n\nMain ne aap ke liye ek page ka free jaiza tayyar kiya hai. Kya main aap ko bhej doon?"
        ),
        "email_short": "Assalam o Alaikum {name} team,\n\n{congrats}Yeh nazar aaya: {problem}. {impact}\n\n{pitch} Kya ek page ka free jaiza bhej doon?",
        "whatsapp_friendly": (
            "Assalam o Alaikum! {congrats_short}Main {me} hoon, {company} se. {name} ke baare mein dekha to yeh nazar "
            "aaya: {problem}. Main ne aasan hal ke saath ek free jaiza banaya hai. Kya yahan bhej doon? 🙂"
        ),
        "whatsapp_short": "Assalam o Alaikum! {congrats_short}{name}: {problem}. Free jaiza bhej doon? 🙂",
        "followup_1": "Dobara salam, shayad mera message dab gaya ho. {name} ke liye free jaiza bhejne mein khushi hogi, koi shart nahi.",
        "followup_2": "Yeh meri aakhri yaad-dehani hai. Agar abhi yeh tarjeeh nahi to koi baat nahi, offer qaim rahegi.",
        "footer_unsubscribe": 'Dilchaspi nahi? "unsubscribe" likh kar jawab dein, dobara rabta nahi hoga.',
    },
}


def signal_text(code: str, key: str) -> tuple[str, str, str]:
    table = SIGNAL_TEXT.get(code, SIGNAL_TEXT["en"])
    return table.get(key) or SIGNAL_TEXT["en"][key]


def _lc(code: str, text: str) -> str:
    """Mid-sentence casing for Latin scripts; acronyms like HTTPS survive."""
    return text[:1].lower() + text[1:] if code != "ur" else text


def render(code: str, tone: str, biz_name: str, sender_name: str, company: str, pitch: str,
           problem_keys: list[str], is_new: bool) -> dict[str, str]:
    m = MESSAGES[code]
    tone = tone if tone in ("friendly", "short") else "friendly"
    problems = [signal_text(code, k) for k in problem_keys]
    first = problems[0] if problems else (GENERIC_PROBLEM[code], "", pitch)
    ctx = {
        "name": biz_name, "me": sender_name, "company": company, "pitch": pitch,
        "problem": _lc(code, first[0]), "impact": first[1], "fix": first[2] if problems else "",
        "problem2": _lc(code, problems[1][0]) if len(problems) > 1 else "",
    }
    ctx["congrats"] = m["congrats"].format(**ctx) if is_new else ""
    ctx["congrats_short"] = m["congrats_short"] if is_new else ""
    ctx["extra"] = m["extra"].format(**ctx) if len(problems) > 1 else ""
    email = m[f"email_{tone}"].format(**ctx)
    return {
        "subject": m["subject"].format(**ctx),
        "email": "\n".join(line.strip() for line in email.splitlines()).replace("  ", " "),
        "whatsapp": m[f"whatsapp_{tone}"].format(**ctx).replace("  ", " "),
        "followup_1": m["followup_1"].format(**ctx),
        "followup_2": m["followup_2"].format(**ctx),
    }
