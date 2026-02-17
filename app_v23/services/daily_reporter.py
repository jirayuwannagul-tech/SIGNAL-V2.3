# app_v23/services/daily_reporter.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

# repo root: .../signal 2.3
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_STATS_FILE = _DATA_DIR / "daily_stats.json"
_POSITIONS_FILE = _DATA_DIR / "positions_clean.json"


def _tz() -> ZoneInfo:
    name = (os.getenv("SCHED_TZ", "Asia/Bangkok") or "Asia/Bangkok").strip()
    return ZoneInfo(name)


def _today_key() -> str:
    return datetime.now(_tz()).strftime("%Y-%m-%d")


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8") or "{}") or default
    except Exception:
        return default


def _write_json_atomic(path: Path, obj: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _count_active_positions() -> int:
    data = _read_json(_POSITIONS_FILE, {"positions": {}})
    positions = data.get("positions") or {}
    return len(positions) if isinstance(positions, dict) else 0


@dataclass
class DailyStats:
    scanned: int = 0
    signals: int = 0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DailyStats":
        return DailyStats(
            scanned=int(d.get("scanned", 0) or 0),
            signals=int(d.get("signals", 0) or 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"scanned": int(self.scanned), "signals": int(self.signals)}


def load_stats_for_today() -> DailyStats:
    _ensure_data_dir()
    key = _today_key()
    root = _read_json(_STATS_FILE, {"days": {}})
    days = root.get("days") or {}
    day = days.get(key) or {}
    return DailyStats.from_dict(day)


def save_stats_for_today(stats: DailyStats) -> None:
    _ensure_data_dir()
    key = _today_key()
    root = _read_json(_STATS_FILE, {"days": {}})
    if "days" not in root or not isinstance(root["days"], dict):
        root["days"] = {}
    root["days"][key] = stats.to_dict()
    _write_json_atomic(_STATS_FILE, root)


def record_scan(count: int) -> None:
    s = load_stats_for_today()
    s.scanned += int(count or 0)
    save_stats_for_today(s)


def record_signal() -> None:
    s = load_stats_for_today()
    s.signals += 1
    save_stats_for_today(s)


def format_daily_summary_message() -> str:
    d = _today_key()
    now_th = datetime.now(_tz()).strftime("%H:%M")
    s = load_stats_for_today()
    active = _count_active_positions()

    return (
        "📊 DAILY SUMMARY (1D)\n\n"
        f"📅 Date: {d}\n"
        f"🕗 Time: {now_th} (Asia/Bangkok)\n"
        f"🔎 Scanned Today: {s.scanned}\n"
        f"📈 Signals Today: {s.signals}\n"
        f"📌 Active Positions: {active}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💎 SIGNAL V2.3"
    )


def get_daily_summary_payload() -> Dict[str, Any]:
    d = _today_key()
    s = load_stats_for_today()
    active = _count_active_positions()
    return {
        "date": d,
        "scanned_today": int(s.scanned),
        "signals_today": int(s.signals),
        "active_positions": int(active),
    }