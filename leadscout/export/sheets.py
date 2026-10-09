"""Export to Google Sheets (free). Needs `pip install "leadscout[sheets]"`,
a Google service-account JSON key (GOOGLE_SERVICE_ACCOUNT_FILE) and the
sheet shared with the service account's email address."""
from __future__ import annotations

import os

from ..config import Campaign
from ..db import DB
from .csv import COLUMNS, lead_rows


def export_sheet(db: DB, campaign: Campaign, spreadsheet_id: str, worksheet: str | None = None) -> str:
    try:
        import gspread
    except ImportError as e:
        raise RuntimeError('Install the Sheets extra: pip install "leadscout[sheets]"') from e
    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not key_file:
        raise RuntimeError("Set GOOGLE_SERVICE_ACCOUNT_FILE to your service-account JSON key path")
    gc = gspread.service_account(filename=key_file)
    sh = gc.open_by_key(spreadsheet_id)
    title = worksheet or campaign.name[:90]
    try:
        ws = sh.worksheet(title)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(COLUMNS))
    values = [COLUMNS] + [["" if r[c] is None else r[c] for c in COLUMNS] for r in lead_rows(db, campaign)]
    ws.update(values, "A1")
    return sh.url
