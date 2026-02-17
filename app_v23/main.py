# app_v23/main.py
from __future__ import annotations

import os
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, request

from app_v23.run_once import run_once

app = Flask(__name__)

# กันยิงซ้อน (process-level)
_RUNNING = False

# ไฟล์รายชื่อเหรียญ
SYMBOLS_FILE = Path(__file__).resolve().parent / "config" / "symbols.txt"


def _load_symbols() -> list[str]:
    if not SYMBOLS_FILE.exists():
        return ["BTCUSDT"]

    raw = SYMBOLS_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return ["BTCUSDT"]

    parts: list[str] = []
    for chunk in raw.replace("\n", ",").split(","):
        s = chunk.strip().upper()
        if s:
            parts.append(s)

    seen = set()
    out: list[str] = []
    for s in parts:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out or ["BTCUSDT"]


def _require_key() -> tuple[bool, str]:
    key = (os.getenv("RUN_DAILY_KEY", "") or "").strip()
    if not key:
        return True, ""  # dev mode
    got = (request.args.get("key", "") or "").strip()
    if got != key:
        return False, "INVALID_KEY"
    return True, ""


@app.get("/")
def root():
    return jsonify({"ok": True, "service": "SIGNAL-V2.3"})


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.post("/run-daily")
def run_daily():
    global _RUNNING

    ok, err = _require_key()
    if not ok:
        return jsonify({"ok": False, "error": err}), 401

    if _RUNNING:
        return jsonify({"ok": False, "error": "ALREADY_RUNNING"}), 409

    _RUNNING = True
    t0 = time.time()
    try:
        timeframe = (request.args.get("timeframe") or "1d").lower()
        limit = int(request.args.get("limit") or "200")

        # 1) ถ้าส่ง symbol มา → รันตัวเดียว
        one = (request.args.get("symbol") or "").strip().upper()
        symbols = [one] if one else _load_symbols()

        # 2) ถ้าส่ง symbols=BTCUSDT,ETHUSDT,... → override list
        symbols_param = (request.args.get("symbols") or "").strip()
        if symbols_param:
            symbols = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]

        for sym in symbols:
            run_once(sym, timeframe, limit=limit)

        return jsonify(
            {
                "ok": True,
                "timeframe": timeframe,
                "symbols_count": len(symbols),
                "elapsed_sec": round(time.time() - t0, 2),
            }
        )
    finally:
        _RUNNING = False


# =========================
# Internal daily scheduler
# =========================
def _bool_env(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _run_daily_job() -> None:
    """Run scan once per day (07:05 TH by default)."""
    global _RUNNING
    if _RUNNING:
        return

    _RUNNING = True
    try:
        timeframe = (os.getenv("RUN_DAILY_TIMEFRAME", "1d") or "1d").strip().lower()
        limit = int(os.getenv("RUN_DAILY_LIMIT", "200") or "200")

        symbols = _load_symbols()
        for sym in symbols:
            run_once(sym, timeframe, limit=limit)
    finally:
        _RUNNING = False


def _start_scheduler_if_enabled() -> None:
    if not _bool_env("ENABLE_INTERNAL_SCHEDULER", "0"):
        return

    tz = (os.getenv("SCHED_TZ", "Asia/Bangkok") or "Asia/Bangkok").strip()
    hhmm = (os.getenv("RUN_DAILY_AT", "07:05") or "07:05").strip()

    try:
        hour_s, min_s = hhmm.split(":", 1)
        hour = int(hour_s)
        minute = int(min_s)
    except Exception:
        hour, minute = 7, 5

    sched = BackgroundScheduler(timezone=tz)
    sched.add_job(_run_daily_job, "cron", hour=hour, minute=minute, id="run_daily_0705", replace_existing=True)
    sched.start()


# ให้ gunicorn import แล้ว scheduler เริ่มทำงานทันที
_start_scheduler_if_enabled()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)