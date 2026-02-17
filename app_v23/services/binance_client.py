# app_v23/services/binance_client.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional
import time
import requests


BINANCE_BASE_URL = "https://api.binance.com"


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time_ms: int


def fetch_ohlcv(
    symbol: str,
    interval: str,
    limit: int = 500,
    start_time_ms: Optional[int] = None,
    end_time_ms: Optional[int] = None,
    timeout_sec: int = 15,
) -> List[Candle]:
    """
    Fetch OHLCV candles from Binance Klines endpoint.
    interval examples: "1d", "15m"
    """
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": int(limit),
    }
    if start_time_ms is not None:
        params["startTime"] = int(start_time_ms)
    if end_time_ms is not None:
        params["endTime"] = int(end_time_ms)

    url = f"{BINANCE_BASE_URL}/api/v3/klines"

    try:
        resp = requests.get(url, params=params, timeout=timeout_sec)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Binance fetch_ohlcv failed: {e}") from e

    candles: List[Candle] = []
    for row in data:
        # row layout (Binance): [
        # 0 openTime, 1 open, 2 high, 3 low, 4 close, 5 volume,
        # 6 closeTime, 7 quoteAssetVolume, 8 numberOfTrades,
        # 9 takerBuyBaseAssetVolume, 10 takerBuyQuoteAssetVolume, 11 ignore
        # ]
        candles.append(
            Candle(
                open_time_ms=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                close_time_ms=int(row[6]),
            )
        )
    return candles


def candles_to_dicts(candles: List[Candle]) -> List[Dict]:
    """Utility: convert Candle objects to plain dicts (ง่ายต่อการส่งต่อ)."""
    return [
        {
            "open_time_ms": c.open_time_ms,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "close_time_ms": c.close_time_ms,
        }
        for c in candles
    ]

def fetch_last_price(symbol: str, timeout_sec: int = 10) -> float:
    url = f"{BINANCE_BASE_URL}/api/v3/ticker/price"
    try:
        r = requests.get(url, params={"symbol": symbol.upper()}, timeout=timeout_sec)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        raise RuntimeError(f"Binance fetch_last_price failed: {e}") from e

if __name__ == "__main__":
    # quick smoke test
    cs = fetch_ohlcv("BTCUSDT", "1d", limit=5)
    print(candles_to_dicts(cs)[-1])