"""Catalog of "fixable problem" signals the audit can detect.

Each signal has a short title, why it hurts the business (used as pitch
evidence) and the fix you can offer.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    title: str
    impact: str
    fix: str


SIGNALS: dict[str, Signal] = {
    "new_business": Signal(
        "Recently opened",
        "New businesses are still building their online presence, and the first months decide whether locals find them.",
        "A launch package: website, Google Business Profile, and a plan to collect the first reviews.",
    ),
    "no_website": Signal(
        "No website",
        "Customers searching online can't find your menu, services, prices or hours, so they pick a competitor who has a site.",
        "A simple, fast website with your services, location map, hours and a click-to-call / WhatsApp button.",
    ),
    "social_only": Signal(
        "Only a Facebook/Instagram page as the website",
        "Social pages rank poorly on Google and you don't own the audience or the layout.",
        "Your own domain and website that links to your social pages.",
    ),
    "free_subdomain": Signal(
        "Website on a free subdomain",
        "Addresses like name.wixsite.com or name.blogspot.com look less trustworthy and are harder to remember.",
        "Move to your own domain name, for example yourbusiness.com.",
    ),
    "site_down": Signal(
        "Website is down or returns errors",
        "Visitors who click your link from Google or Maps land on an error page and leave.",
        "Fix hosting and DNS and add uptime monitoring.",
    ),
    "no_https": Signal(
        "No HTTPS (not secure)",
        "Browsers show a 'Not secure' warning, which scares visitors away and hurts Google ranking.",
        "Install a free SSL certificate and redirect all traffic to HTTPS.",
    ),
    "not_mobile_friendly": Signal(
        "Not mobile-friendly",
        "Most local searches happen on phones. Without a responsive layout the site is hard to use on mobile.",
        "A responsive redesign that works well on every screen size.",
    ),
    "slow_site": Signal(
        "Slow website",
        "Slow pages lose visitors before they load and rank lower on Google.",
        "Image compression, caching and lighter pages to load in under 2–3 seconds.",
    ),
    "outdated_copyright": Signal(
        "Website looks outdated",
        "An old copyright year in the footer signals the site isn't maintained, and visitors lose trust.",
        "Refresh the design and content and keep it updated.",
    ),
    "no_contact_form": Signal(
        "No contact form",
        "Visitors who don't want to call have no easy way to reach you, so leads are lost after hours.",
        "Add a contact or enquiry form that sends straight to your email or WhatsApp.",
    ),
    "no_booking": Signal(
        "No online booking or ordering",
        "Customers expect to book or order online 24/7. Without it, bookings go to competitors that offer it.",
        "Add online booking, reservations or ordering.",
    ),
    "no_social_links": Signal(
        "No social media links",
        "Visitors can't follow you or see recent activity, reviews and photos.",
        "Link your social profiles and show recent posts on the site.",
    ),
    "missing_seo_basics": Signal(
        "Missing basic SEO (title/description)",
        "Google shows a poor or random snippet for your site, so fewer people click it.",
        "Proper page titles, meta descriptions and local SEO setup.",
    ),
    "low_rating": Signal(
        "Low Google rating",
        "A rating under 4.0 makes many customers skip you in Maps results.",
        "A review-generation and reply system to raise the rating.",
    ),
    "few_reviews": Signal(
        "Few Google reviews",
        "Businesses with few reviews look less established than nearby competitors.",
        "An automated review-request flow (SMS/WhatsApp/QR code) after each visit.",
    ),
    "no_email_found": Signal(
        "No public email address",
        "Customers and partners can't easily reach you in writing.",
        "A professional email on your own domain, shown on the website.",
    ),
}


def describe(keys: list[str]) -> list[dict[str, str]]:
    return [{"key": k, "title": SIGNALS[k].title, "impact": SIGNALS[k].impact, "fix": SIGNALS[k].fix}
            for k in keys if k in SIGNALS]
