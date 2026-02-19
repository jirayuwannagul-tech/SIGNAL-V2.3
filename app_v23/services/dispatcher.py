# app_v23/services/dispatcher.py
from __future__ import annotations

import os
import requests

from app_v23.core.indicator_engine import SignalPayload
from app_v23.services.daily_reporter import record_signal
from app_v23.services.sheets_logger import append_signal_row, append_daily_summary_row


def _format_tg_message(p: SignalPayload) -> str:
    return (
        f"🚨 SIGNAL {p.timeframe} {p.symbol}\n"
        f"Direction: {p.direction}\n"
        f"Entry: {p.entry_price:.4f}\n"
        f"SL: {p.stop_loss:.4f}\n"
        f"TP1: {p.tp1:.4f}\n"
        f"TP2: {p.tp2:.4f}\n"
        f"TP3: {p.tp3:.4f}\n"
        f"Reason: {p.reason}\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💎 SIGNAL V2.3"
    )

def send_telegram_text(text: str, topic_env: str = "TOPIC_NORMAL_ID") -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    topic_id = (os.getenv(topic_env, "") or "").strip()
    if topic_id:
        try:
            payload["message_thread_id"] = int(topic_id)
        except Exception:
            pass

    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()


def send_telegram(payload: SignalPayload) -> None:
    send_telegram_text(_format_tg_message(payload), topic_env="TOPIC_VIP_ID")


def send_daily_summary_to_telegram(text: str) -> None:
    topic_env = (os.getenv("DAILY_REPORT_TOPIC_ENV", "TOPIC_VIP_ID") or "TOPIC_VIP_ID").strip()
    send_telegram_text(text, topic_env=topic_env)


def dispatch(payload: SignalPayload) -> None:
    # Telegram
    send_telegram(payload)

    # daily stats
    record_signal()

    # Sheet
    try:
        append_signal_row(payload, sheet_name=os.getenv("GOOGLE_SHEET_TAB", "Signals"))
        print("SHEET_LOGGED")
    except Exception as e:
        print(f"SHEET_SKIPPED: {e}")


def dispatch_daily_summary_to_sheet(summary: dict) -> None:
    try:
        append_daily_summary_row(
            summary,
            sheet_name=os.getenv("GOOGLE_SHEET_DAILY_TAB", "Daily"),
        )
        print("SHEET_DAILY_SUMMARY_LOGGED")
    except Exception as e:
        print(f"SHEET_DAILY_SUMMARY_SKIPPED: {e}")