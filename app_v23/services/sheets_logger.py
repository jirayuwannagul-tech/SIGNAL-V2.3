from __future__ import annotations

import os
from typing import List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app_v23.core.indicator_engine import SignalPayload

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# =========================
# ENV + SERVICE
# =========================
def _get_env(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing {name}")
    return v


def _svc():
    spreadsheet_id = _get_env("GOOGLE_SHEETS_ID")
    cred_path = _get_env("GOOGLE_CREDENTIALS_PATH")

    creds = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=SCOPES,
    )

    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return service, spreadsheet_id


# =========================
# SIGNAL ROW (Signals Tab)
# =========================
def append_signal_row(payload: SignalPayload, sheet_name: str = "Signals") -> None:
    service, spreadsheet_id = _svc()

    values: List[List[object]] = [[
        "=NOW()",
        payload.symbol,
        payload.timeframe,
        payload.direction,
        payload.entry_price,
        payload.stop_loss,
        payload.tp1,
        payload.tp2,
        payload.tp3,
        False,
        False,
        False,
        False,
        "ACTIVE",
        payload.reason,
    ]]

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:O",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


# =========================
# UPDATE TP/SL STATUS
# =========================
def _find_latest_active_row(
    sheet_name: str,
    symbol: str,
    timeframe: str,
    direction: str,
) -> Optional[int]:
    service, spreadsheet_id = _svc()

    resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!B:O",
    ).execute()

    rows = resp.get("values") or []
    if not rows:
        return None

    sym = symbol.strip().upper()
    tf = timeframe.strip()
    dirn = direction.strip().upper()

    for idx in range(len(rows) - 1, -1, -1):
        r = rows[idx]
        r_sym = (r[0] if len(r) > 0 else "").strip().upper()
        r_tf = (r[1] if len(r) > 1 else "").strip()
        r_dir = (r[2] if len(r) > 2 else "").strip().upper()
        r_status = (r[12] if len(r) > 12 else "").strip().upper()

        if r_sym == sym and r_tf == tf and r_dir == dirn and r_status == "ACTIVE":
            return idx + 1

    return None


def update_hit_status(
    sheet_name: str,
    symbol: str,
    timeframe: str,
    direction: str,
    tp1_hit: bool,
    tp2_hit: bool,
    tp3_hit: bool,
    sl_hit: bool,
    status: str,
) -> bool:
    service, spreadsheet_id = _svc()

    row = _find_latest_active_row(sheet_name, symbol, timeframe, direction)
    if not row:
        return False

    values = [[
        bool(tp1_hit),
        bool(tp2_hit),
        bool(tp3_hit),
        bool(sl_hit),
        status,
    ]]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!J{row}:N{row}",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()

    return True   # ✅ สำคัญ: ต้องจบตรงนี้


# =========================
# DAILY SUMMARY (Daily Tab)
# =========================
def append_daily_summary_row(summary: dict, sheet_name: str = "Daily") -> None:
    service, spreadsheet_id = _svc()

    values: List[List[object]] = [[
        "=NOW()",
        summary.get("date", ""),
        int(summary.get("scanned_today", 0) or 0),
        int(summary.get("signals_today", 0) or 0),
        int(summary.get("active_positions", 0) or 0),
    ]]

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:E",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()