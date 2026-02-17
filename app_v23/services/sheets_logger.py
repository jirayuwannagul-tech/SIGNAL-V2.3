from __future__ import annotations

import os
from typing import List, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app_v23.core.indicator_engine import SignalPayload

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_env(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing {name}")
    return v


def _svc():
    spreadsheet_id = _get_env("GOOGLE_SHEETS_ID")
    cred_path = _get_env("GOOGLE_CREDENTIALS_PATH")
    creds = service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return service, spreadsheet_id


# Columns (Signals tab):
# A timestamp
# B symbol
# C timeframe
# D direction
# E entry
# F sl
# G tp1
# H tp2
# I tp3
# J tp1_hit
# K tp2_hit
# L tp3_hit
# M sl_hit
# N status
# O reason

def append_signal_row(payload: SignalPayload, sheet_name: str = "Signals") -> None:
    service, spreadsheet_id = _svc()

    values: List[List[object]] = [[
        "=NOW()",                 # timestamp in sheet time
        payload.symbol,
        payload.timeframe,
        payload.direction,
        payload.entry_price,
        payload.stop_loss,
        payload.tp1,
        payload.tp2,
        payload.tp3,
        False,                    # tp1_hit
        False,                    # tp2_hit
        False,                    # tp3_hit
        False,                    # sl_hit
        "ACTIVE",                 # status
        payload.reason,
    ]]

    body = {"values": values}
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:O",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def _find_latest_active_row(
    sheet_name: str,
    symbol: str,
    timeframe: str,
    direction: str,
) -> Optional[int]:
    """
    หาแถวล่าสุดที่ตรง (symbol,timeframe,direction) และ status=ACTIVE
    return: row_number (1-based) หรือ None
    """
    service, spreadsheet_id = _svc()

    # read B:O (skip timestamp col A)
    resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!B:O",
    ).execute()

    rows = resp.get("values") or []
    if not rows:
        return None

    # rows[0] is header if you put header; we still scan from bottom safely
    sym = symbol.strip().upper()
    tf = timeframe.strip()
    dirn = direction.strip().upper()

    for idx in range(len(rows) - 1, -1, -1):
        r = rows[idx]
        r_sym = (r[0] if len(r) > 0 else "").strip().upper()  # col B
        r_tf = (r[1] if len(r) > 1 else "").strip()          # col C
        r_dir = (r[2] if len(r) > 2 else "").strip().upper() # col D
        r_status = (r[12] if len(r) > 12 else "").strip().upper()  # col N (B->N = index 12)

        if r_sym == sym and r_tf == tf and r_dir == dirn and r_status == "ACTIVE":
            # +1 because rows is 0-based, +1 because sheet rows start at 1
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
    """
    อัปเดตคอลัมน์ J:N ของแถว ACTIVE ล่าสุด
    return True ถ้าอัปเดตได้, False ถ้าไม่เจอแถว
    """
    service, spreadsheet_id = _svc()

    row = _find_latest_active_row(sheet_name, symbol, timeframe, direction)
    if not row:
        return False

    # J..N = 5 columns
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

    return True