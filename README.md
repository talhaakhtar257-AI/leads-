# LeadScout

**An AI agent that finds local businesses with a visible, fixable problem, proves the problem with an audit, and writes the pitch for you.**

Most lead tools give you a *list* of businesses. LeadScout tells you **why this business needs you right now**: it checks for no website, a site that is down, no HTTPS, a site that isn't mobile-friendly, no online booking, a low Google rating and more. It then scores every lead for *the service you sell* and drafts outreach that cites those real findings.

It costs **$0 to start**: OpenStreetMap for discovery, free LLM tiers (or no LLM at all), and Gmail for sending.

## No terminal needed

1. Install [Python 3.10 or newer](https://www.python.org/downloads/). On Windows, tick **"Add python.exe to PATH"** in the installer.
2. On GitHub, click **Code → Download ZIP**, then unzip it.
3. Double-click the launcher in the unzipped folder:
   - **Windows:** `start.bat`
   - **Mac:** `start.command` (the first time, right-click it, choose **Open**, then confirm)
   - **Linux:** `start.sh`
4. The first run takes a minute while it installs. After that, the dashboard opens in your browser.
5. Open **Settings** in the dashboard to set your city, categories, the service you sell, and your name and address.
6. To add API keys (an AI writer, Gmail for sending, extra sources), open the `.env` file in the same folder with any text editor (Notepad, TextEdit), paste the keys after the `=` signs, save, and restart the launcher.

Keep the launcher window open while you use LeadScout. Closing it stops the dashboard.

## What the agent does

| # | Job | Command |
|---|-----|---------|
| 1 | **Discover** businesses by category and area from OpenStreetMap (free), Google Places, Foursquare and Yelp. Duplicates are merged across sources and campaigns, so each source fills in what the others missed | `leadscout discover` |
| 2 | **Audit** each web presence for fixable problems ([full list](leadscout/signals.py)), and spot **recently opened** businesses, the hottest leads | `leadscout audit` |
| 3 | **Enrich** contacts: emails (MX-checked), phones, Facebook, Instagram and WhatsApp, read from the site and its contact pages | (part of audit) |
| 4 | **Score 0–100** for *your* service (`web_design`, `seo`, `booking_system`, `social_media`, `reputation`, `maintenance`, `general_marketing`). A lead you can't contact is capped at 20 | `leadscout score` |
| 5 | **Draft** an email, a WhatsApp message and 2 follow-ups in any language, citing only real findings | `leadscout draft` |
| 6 | **Mini audit page** per lead (`output/audits/*.html`): the evidence you can share | (part of draft) |
| 7 | **Review gate**: approve, edit or skip every draft. Nothing is sent without approval | `leadscout review` |
| 8 | **Send email** within a daily cap and random delays. Follow-ups go out on day 3 and day 7 | `leadscout send` |
| 9 | **WhatsApp**: one-click `wa.me` links with the message pre-filled | `leadscout whatsapp` |
| 10 | **Reply detection** (IMAP): stops follow-ups when a lead replies and honors "unsubscribe" | `leadscout check-replies` |
| 11 | **Export** to CSV, Google Sheets or HubSpot | `leadscout export --to csv\|sheets\|hubspot` |
| 12 | **Report**: the funnel and the most common problems in the area | `leadscout report` |
| 13 | **Lead packs** to sell: a zip with `leads.csv` and a PDF market report per niche | `leadscout pack --niche cafe` |

`leadscout run` chains steps 1–6 and writes `output/<campaign>.csv`.

## Quick start

```bash
git clone https://github.com/talhaakhtar257-ai/leads-.git && cd leads-
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
leadscout init            # creates campaign.yaml and .env
# edit campaign.yaml: location, categories, service, your name/address
leadscout run -n 20       # small first run
leadscout leads           # best leads first
leadscout review          # approve drafts
leadscout send --dry-run  # see exactly what would be sent
leadscout send            # needs SMTP_* in .env
leadscout whatsapp        # open WhatsApp links and send them by hand
```

Run `leadscout check-replies` and `leadscout send` once a day, for example with cron: `0 10 * * * cd /path/to/leads- && .venv/bin/leadscout check-replies && .venv/bin/leadscout send`.

## Web dashboard

Prefer clicking to typing? Start the dashboard:

```bash
pip install -e ".[web]"
leadscout web             # opens on http://localhost:8000
```

- **Dashboard:** run any step with one click and watch the live log, plus lead counts, the most common problems in the area, and the pipeline from new to won.
- **Leads:** search and filter, see every lead on a map colored by score, and download a CSV.
- **Lead page:** why it's a good lead, the evidence, contacts, the 1-page audit, and status updates (replied, won, lost, unsubscribed).
- **Review:** edit, approve or skip drafts. Follow-ups are approved together with the first message.
- **WhatsApp:** open each chat with the message already filled in, then mark it as sent.
- **Settings:** edit the campaign; it's checked before saving. Switch between campaign files from the top bar.

The dashboard has no login and listens only on your own computer by default. Only use `--host 0.0.0.0` on a network you trust.

## Free setup choices

| Need | Free option |
|------|-------------|
| Business data | OpenStreetMap (default, no key). Add more with `sources: [overpass, google_places, foursquare]`: Google Places adds ratings and reviews (free monthly quota, `GOOGLE_PLACES_API_KEY`), Foursquare adds phones and websites (free monthly allowance, `FOURSQUARE_API_KEY`). Yelp (`YELP_API_KEY`) is **paid** after a trial, and its terms limit how long you may keep its data |
| AI writer | `GEMINI_API_KEY` (Google AI Studio free tier), `GROQ_API_KEY` (free tier), or `OLLAMA_MODEL` (local). With no key, built-in English templates are used |
| Best writing quality (paid) | `ANTHROPIC_API_KEY` + `pip install -e ".[claude]"` |
| Email | Gmail with an [app password](https://support.google.com/accounts/answer/185833) (`SMTP_USER`, `SMTP_PASSWORD`) |
| Google Sheets | `pip install -e ".[sheets]"` + a service-account JSON key |
| CRM | HubSpot free CRM (`HUBSPOT_TOKEN`) |

`llm: auto` picks the first configured key in this order: Claude, Gemini, Groq, Ollama, then templates.

**Categories:** `restaurant, cafe, fast_food, bakery, dentist, clinic, doctor, pharmacy, salon, beauty, gym, hotel, car_repair, real_estate, lawyer, accountant, school, tutor, vet, florist, clothes, electronics, furniture, optician, travel_agency`, or any raw OSM tag such as `shop=tailor`.

## New businesses

A business counts as **recently opened** when any of these is true:
- OpenStreetMap gives an opening date (`start_date`) in the last 12 months.
- It was first added to OpenStreetMap in the last 6 months.
- Google Places shows fewer than 10 reviews.

New owners still need a website, a Google profile and their first reviews, so these leads score higher, and drafts open with a congratulations. Tick **New businesses only** on the dashboard's Leads page to see just them.

## Lead packs

Sell leads to agencies: `pip install -e ".[packs]"`, then:

```bash
leadscout pack --niche dentist --min-score 50 --business-emails-only
```

This writes `output/packs/<campaign>-<niche>-<date>.zip` with:
- `leads.csv`: business, score, problems, contacts.
- `report.pdf`: a cover, how common each problem is in the area, the lead table, and how the data was collected.

Your outreach status and WhatsApp drafts stay out of the pack, and anyone who opted out is removed. The dashboard's Leads page has the same option under **Download a lead pack**.

**Selling contact data is regulated in many places** (for example GDPR in the EU and UK). `--business-emails-only` leaves out personal-looking addresses such as gmail. Check the rules where you and your buyers operate.

## Play fair (and stay out of spam folders)

- Every email includes your name, your postal address and an unsubscribe line, plus a `List-Unsubscribe` header.
- A suppression list (`leadscout suppress <email|phone>`) and reply detection make sure people who opt out are never contacted again.
- Keep `daily_emails` low on a new mailbox (20–30) and increase it slowly.
- WhatsApp messages are sent **by you**, one click at a time. Automating personal WhatsApp accounts breaks WhatsApp's terms and gets numbers banned.
- Check the cold-outreach rules where you operate (for example CAN-SPAM in the US, GDPR/PECR in the EU and UK).

## Development

```bash
pip install -e ".[dev]"
pytest
```

Layout: `leadscout/sources` (discovery), `audit` (signal detection), `enrich` (contacts), `scoring.py`, `llm` (providers), `outreach` (drafts, email, WhatsApp, follow-ups), `reports`, `export`, `web` (dashboard), `cli.py`.
