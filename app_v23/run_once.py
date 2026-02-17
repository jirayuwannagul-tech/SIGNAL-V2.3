# app_v22_clean/run_once.py
from __future__ import annotations

import sys
import time

from app_v22_clean.services.binance_client import fetch_ohlcv, candles_to_dicts, fetch_last_price
from app_v22_clean.core.indicator_engine import analyze_candles_for_signal
from app_v22_clean.services.dispatcher import dispatch
from app_v22_clean.services.position_store import (
    is_locked,
    create_position,
    update_on_price,
    get_last_emitted_close_time_ms,
    set_last_emitted_close_time_ms,
)


def run_once(symbol: str, timeframe: str, limit: int = 200) -> int:
    # ✅ ใช้แค่ 1D
    if timeframe.lower() != "1d":
        print("ONLY_1D_ALLOWED")
        return 0

    candles = candles_to_dicts(fetch_ohlcv(symbol, timeframe, limit=limit))
    now_ms = int(time.time() * 1000)

    # ✅ ใช้แท่งปิดแล้วเสมอ: ถ้าแท่งล่าสุดยังไม่ปิด -> ทิ้งมัน
    last_close_time_ms = int(candles[-1]["close_time_ms"])
    if now_ms <= last_close_time_ms:
        candles = candles[:-1]
        if len(candles) < 60:
            print("NOT_ENOUGH_CLOSED_CANDLES")
            return 0
        last_close_time_ms = int(candles[-1]["close_time_ms"])

    # ✅ ยิงครั้งเดียวต่อแท่ง
    last_emitted = get_last_emitted_close_time_ms(symbol, timeframe)
    if last_emitted == last_close_time_ms:
        print("ALREADY_EMITTED_THIS_CANDLE")
        return 0

    # 🔒 ถ้ามี ACTIVE → อัปเดตราคาเพื่อปลดล็อกก่อน (ปลดเฉพาะ SL หรือ TP3)
    if is_locked(symbol, timeframe):
        last = fetch_last_price(symbol)
        st = update_on_price(symbol, timeframe, last)
        print(f"POSITION_UPDATE: {st} last={last}")
        if st != "CLOSED":
            print("LOCKED_SKIP")
            return 0

    sig = analyze_candles_for_signal(symbol, timeframe, candles)
    if not sig:
        print("NO_SIGNAL")
        return 0

    print(f"SIGNAL: {sig}")
    dispatch(sig)
    create_position(sig)

    # ✅ จำว่าแท่งนี้ยิงไปแล้ว
    set_last_emitted_close_time_ms(symbol, timeframe, last_close_time_ms)

    print("DISPATCHED")
    return 0


if __name__ == "__main__":
    # usage: python -m app_v22_clean.run_once BTCUSDT 1d
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1d"
    raise SystemExit(run_once(symbol, tf))