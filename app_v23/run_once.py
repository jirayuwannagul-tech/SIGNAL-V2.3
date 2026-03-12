# app_v23/run_once.py
from __future__ import annotations

import os
import sys
import time

from app_v23.services.binance_client import fetch_ohlcv, candles_to_dicts, fetch_last_price
from app_v23.core.indicator_engine import analyze_candles_for_signal
from app_v23.services.dispatcher import dispatch
from app_v23.services.position_store import (
    is_locked,
    create_position,
    update_on_price,
    get_last_emitted_close_time_ms,
    set_last_emitted_close_time_ms,
)

# Return codes
RC_SUCCESS        = 0
RC_SKIP           = 1   # ข้ามแบบปกติ (no signal, already emitted, locked)
RC_INVALID_INPUT  = 2   # timeframe ไม่รองรับ / candle ไม่พอ
RC_ERROR          = 3   # exception ที่ไม่คาดคิด


def _configured_fixed_timeframe() -> str | None:
    value = (os.getenv("CDC_FIXED_TIMEFRAME", "") or "").strip()
    return value or None


def _effective_signal_timeframe(timeframe: str, fixed_timeframe: str | None) -> str:
    return (fixed_timeframe or timeframe).strip()


def run_once(symbol: str, timeframe: str, limit: int = 200, fixed_timeframe: str | None = None) -> int:
    fixed_timeframe = (fixed_timeframe or _configured_fixed_timeframe() or "").strip() or None
    effective_timeframe = _effective_signal_timeframe(timeframe, fixed_timeframe)

    # ✅ default mode ใช้แค่ 1D; ถ้าเปิด fixed timeframe mode อนุญาต timeframe อื่นได้
    if fixed_timeframe is None and timeframe.lower() != "1d":
        print("ONLY_1D_ALLOWED")
        return RC_INVALID_INPUT

    candles = candles_to_dicts(fetch_ohlcv(symbol, timeframe, limit=limit))
    now_ms = int(time.time() * 1000)

    # ✅ ใช้แท่งปิดแล้วเสมอ: ถ้าแท่งล่าสุดยังไม่ปิด -> ทิ้งมัน
    last_close_time_ms = int(candles[-1]["close_time_ms"])
    if now_ms <= last_close_time_ms:
        candles = candles[:-1]
        if len(candles) < 60:
            print("NOT_ENOUGH_CLOSED_CANDLES")
            return RC_INVALID_INPUT
        last_close_time_ms = int(candles[-1]["close_time_ms"])

    # ✅ ยิงครั้งเดียวต่อแท่ง
    last_emitted = get_last_emitted_close_time_ms(symbol, effective_timeframe)
    if last_emitted == last_close_time_ms:
        print("ALREADY_EMITTED_THIS_CANDLE")
        return RC_SKIP

    # 🔒 ถ้ามี ACTIVE → อัปเดตราคาเพื่อปลดล็อกก่อน (ปลดเฉพาะ SL หรือ TP3)
    if is_locked(symbol, effective_timeframe):
        last = fetch_last_price(symbol)
        st = update_on_price(symbol, effective_timeframe, last)
        print(f"POSITION_UPDATE: {st} last={last}")
        if st != "CLOSED":
            print("LOCKED_SKIP")
            return RC_SKIP

    sig = analyze_candles_for_signal(symbol, effective_timeframe, candles, fixed_timeframe=fixed_timeframe)
    if not sig:
        print("NO_SIGNAL")
        return RC_SKIP

    print(f"SIGNAL: {sig}")
    dispatch(sig)
    create_position(sig)

    # ✅ จำว่าแท่งนี้ยิงไปแล้ว
    set_last_emitted_close_time_ms(symbol, effective_timeframe, last_close_time_ms)

    print("DISPATCHED")
    return RC_SUCCESS


if __name__ == "__main__":
    # usage: python -m app_v23.run_once BTCUSDT 1d
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1d"
    raise SystemExit(run_once(symbol, tf))
