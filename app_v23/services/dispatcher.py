# app_v23/services/dispatcher.py
from __future__ import annotations

import os
import requests

from app_v23.core.indicator_engine import SignalPayload
from app_v23.services.daily_reporter import record_signal


def _format_tg_message(p: SignalPayload) -> str:
    action = "🟢 ซื้อ (LONG)" if p.direction == "LONG" else "🔴 ขาย (SHORT)"
    return (
        f"📡 CDC ActionZone ตัดแล้ว!\n\n"
        f"💎 {p.symbol} {p.timeframe}\n"
        f"{action}\n"
        f"📍 Entry: {p.entry_price:.4f}\n\n"
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
    send_telegram(payload)
    record_signal()
