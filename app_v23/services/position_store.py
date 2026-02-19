# app_v23/services/position_store.py
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict
from datetime import datetime, timezone
from app_v23.core.indicator_engine import SignalPayload


POSITIONS_FILE = Path("data/positions_clean.json")

_FILE_LOCK = threading.Lock()  # ป้องกัน race condition ภายใน process เดียวกัน


def _key(symbol: str, timeframe: str) -> str:
    return f"{symbol.upper()}::{timeframe}"


def load_positions() -> Dict:
    if not POSITIONS_FILE.exists():
        return {"positions": {}}
    return json.loads(POSITIONS_FILE.read_text(encoding="utf-8") or "{}") or {"positions": {}}


def save_positions(state: Dict) -> None:
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    POSITIONS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_locked(symbol: str, timeframe: str) -> bool:
    with _FILE_LOCK:
        state = load_positions()
    pos = (state.get("positions") or {}).get(_key(symbol, timeframe))
    if not pos:
        return False
    return (pos.get("status") or "").upper() == "ACTIVE"


def create_position(payload: SignalPayload) -> None:
    with _FILE_LOCK:
        state = load_positions()
        positions = state.setdefault("positions", {})
        positions[_key(payload.symbol, payload.timeframe)] = {
            "symbol": payload.symbol,
            "timeframe": payload.timeframe,
            "direction": payload.direction,
            "entry_price": payload.entry_price,
            "stop_loss": payload.stop_loss,
            "tp1": payload.tp1,
            "tp2": payload.tp2,
            "tp3": payload.tp3,
            "status": "ACTIVE",
            "tp1_hit": False,
            "tp2_hit": False,
            "tp3_hit": False,
            "sl_hit": False,
        }
        save_positions(state)


def update_on_price(symbol: str, timeframe: str, last_price: float) -> str:
    """
    return: ACTIVE / CLOSED / NOT_FOUND
    ปิดเฉพาะ SL หรือ TP3
    """
    with _FILE_LOCK:
        state = load_positions()
        positions = state.get("positions") or {}

        k = _key(symbol, timeframe)
        pos = positions.get(k)
        if not pos:
            return "NOT_FOUND"

        if (pos.get("status") or "").upper() != "ACTIVE":
            return "CLOSED"

        direction = (pos.get("direction") or "").upper()
        sl = float(pos.get("stop_loss"))
        tp1 = float(pos.get("tp1"))
        tp2 = float(pos.get("tp2"))
        tp3 = float(pos.get("tp3"))

        now = datetime.now(timezone.utc).isoformat()

        def mark(name: str):
            pos.setdefault("events", {})
            pos["events"][name] = now

        if direction == "LONG":
            if last_price <= sl:
                pos["sl_hit"] = True
                pos["status"] = "CLOSED"
                mark("SL")
            else:
                if last_price >= tp1:
                    pos["tp1_hit"] = True
                    mark("TP1")
                if last_price >= tp2:
                    pos["tp2_hit"] = True
                    mark("TP2")
                if last_price >= tp3:
                    pos["tp3_hit"] = True
                    pos["status"] = "CLOSED"
                    mark("TP3")
        else:  # SHORT
            if last_price >= sl:
                pos["sl_hit"] = True
                pos["status"] = "CLOSED"
                mark("SL")
            else:
                if last_price <= tp1:
                    pos["tp1_hit"] = True
                    mark("TP1")
                if last_price <= tp2:
                    pos["tp2_hit"] = True
                    mark("TP2")
                if last_price <= tp3:
                    pos["tp3_hit"] = True
                    pos["status"] = "CLOSED"
                    mark("TP3")

        pos["last_price"] = float(last_price)
        pos["last_update"] = now

        positions[k] = pos
        state["positions"] = positions
        save_positions(state)

    # ---- update Google Sheet — ทำนอก lock เพราะเป็น network call ----
    try:
        import os
        from app_v23.services.sheets_logger import update_hit_status

        tab = os.getenv("GOOGLE_SHEET_TAB", "Signals")
        update_hit_status(
            sheet_name=tab,
            symbol=pos["symbol"],
            timeframe=pos["timeframe"],
            direction=pos["direction"],
            tp1_hit=bool(pos.get("tp1_hit")),
            tp2_hit=bool(pos.get("tp2_hit")),
            tp3_hit=bool(pos.get("tp3_hit")),
            sl_hit=bool(pos.get("sl_hit")),
            status=str(pos.get("status", "ACTIVE")),
        )
    except Exception as e:
        print(f"SHEET_UPDATE_SKIPPED: {e}")

    return "CLOSED" if (pos.get("status") == "CLOSED") else "ACTIVE"


# ==============================
# Candle emission tracking
# ==============================

def get_last_emitted_close_time_ms(symbol: str, timeframe: str) -> int:
    with _FILE_LOCK:
        state = load_positions()
    meta = state.get("meta") or {}
    last = (meta.get("last_emitted") or {}).get(_key(symbol, timeframe))
    return int(last or 0)


def set_last_emitted_close_time_ms(symbol: str, timeframe: str, close_time_ms: int) -> None:
    with _FILE_LOCK:
        state = load_positions()
        meta = state.setdefault("meta", {})
        last_emitted = meta.setdefault("last_emitted", {})
        last_emitted[_key(symbol, timeframe)] = int(close_time_ms)
        save_positions(state)