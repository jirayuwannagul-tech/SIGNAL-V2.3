# app_v23/services/dispatcher.py
from __future__ import annotations

from dataclasses import asdict
from typing import Optional
import os
import requests

from app_v23.core.indicator_engine import SignalPayload
from app_v23.services.sheets_logger import append_signal_row


def _format_tg_message(p: SignalPayload) -> str:
    # ข้อความสั้น ชัด
    return (
        f"🚨 SIGNAL {p.timeframe} {p.symbol}\n"
        f"Direction: {p.direction}\n"
        f"Entry: {p.entry_price:.4f}\n"
        f"SL: {p.stop_loss:.4f}\n"
        f"TP1: {p.tp1:.4f}\n"
        f"TP2: {p.tp2:.4f}\n"
        f"TP3: {p.tp3:.4f}\n"
        f"Reason: {p.reason}"
    )


def send_telegram(payload: SignalPayload) -> None:
    """
    ต้องตั้ง env:
    - TELEGRAM_BOT_TOKEN
    - TELEGRAM_CHAT_ID
    (topic/thread ค่อยต่อทีหลังได้ แต่ตอนนี้เอาเส้นตรงก่อน)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    msg = _format_tg_message(payload)

    r = requests.post(
        url,
        json={"chat_id": chat_id, "text": msg},
        timeout=15,
    )
    r.raise_for_status()


def dispatch(payload: SignalPayload) -> None:
    # ส่ง Telegram ก่อน
    send_telegram(payload)

    # ยิงเข้า Google Sheet โดยตรง (Service Account)
    try:
        append_signal_row(
            payload,
            sheet_name=os.getenv("GOOGLE_SHEET_TAB", "Sheet1"),
        )
        print("SHEET_LOGGED")
    except Exception as e:
        print(f"SHEET_SKIPPED: {e}")