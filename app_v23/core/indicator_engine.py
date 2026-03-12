# app_v23/core/indicator_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Literal


Direction = Literal["LONG", "SHORT"]
CdcZone = Literal["GREEN", "BLUE", "LBLUE", "RED", "ORANGE", "YELLOW", "NEUTRAL"]


@dataclass(frozen=True)
class SignalPayload:
    symbol: str
    timeframe: str
    direction: Direction
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    reason: str
    zone: CdcZone = "NEUTRAL"


@dataclass(frozen=True)
class CdcSeries:
    xprice: List[float]
    fast: List[Optional[float]]
    slow: List[Optional[float]]
    bull: List[bool]
    bear: List[bool]
    green: List[bool]
    blue: List[bool]
    lblue: List[bool]
    red: List[bool]
    orange: List[bool]
    yellow: List[bool]
    buycond: List[bool]
    sellcond: List[bool]
    bullish: List[bool]
    bearish: List[bool]
    buy: List[bool]
    sell: List[bool]
    zones: List[CdcZone]


def _ema(values: List[float], length: int) -> List[float]:
    if length <= 0:
        raise ValueError("EMA length must be > 0")
    if not values:
        return []
    k = 2 / (length + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append((v * k) + (ema[-1] * (1 - k)))
    return ema


def _ema_optional(values: List[Optional[float]], length: int) -> List[Optional[float]]:
    if length <= 0:
        raise ValueError("EMA length must be > 0")
    if not values:
        return []

    k = 2 / (length + 1)
    out: List[Optional[float]] = []
    prev: Optional[float] = None
    for value in values:
        if value is None:
            out.append(prev)
            continue
        prev = value if prev is None else (value * k) + (prev * (1 - k))
        out.append(prev)
    return out


def _atr(highs: List[float], lows: List[float], closes: List[float], length: int = 14) -> List[float]:
    if len(highs) != len(lows) or len(lows) != len(closes):
        raise ValueError("ATR input lengths mismatch")
    if not highs:
        return []
    trs: List[float] = []
    prev_close = closes[0]
    for h, l, c in zip(highs, lows, closes):
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = c
    return _ema(trs, length)


def _barssince(cond: List[bool]) -> List[int]:
    """
    Pine: ta.barssince(cond)
    - ถ้า cond เป็น True ที่แท่งนั้น -> 0
    - ถ้ายังไม่เคย True มาก่อน -> ค่าใหญ่ (ใช้ 10**9)
    """
    out: List[int] = []
    last_true = None
    for i, v in enumerate(cond):
        if v:
            last_true = i
            out.append(0)
        else:
            out.append(i - last_true if last_true is not None else 10**9)
    return out


def _timeframe_to_ms(timeframe: str) -> int:
    tf = timeframe.strip()
    if not tf:
        raise ValueError("timeframe must not be empty")

    aliases = {
        "D": 24 * 60 * 60 * 1000,
        "W": 7 * 24 * 60 * 60 * 1000,
        "M": 30 * 24 * 60 * 60 * 1000,
    }
    if tf.upper() in aliases:
        return aliases[tf.upper()]

    if tf.isdigit():
        return int(tf) * 60 * 1000

    unit = tf[-1].lower()
    value = tf[:-1]
    if not value.isdigit():
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    qty = int(value)
    if unit == "m":
        return qty * 60 * 1000
    if unit == "h":
        return qty * 60 * 60 * 1000
    if unit == "d":
        return qty * 24 * 60 * 60 * 1000
    if unit == "w":
        return qty * 7 * 24 * 60 * 60 * 1000
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _fixed_tf_ma_series(
    closes: List[float],
    close_times_ms: List[int],
    ema_fast_len: int,
    ema_slow_len: int,
    xsmooth: int,
    fixed_timeframe: str,
) -> tuple[List[Optional[float]], List[Optional[float]]]:
    if len(closes) != len(close_times_ms):
        raise ValueError("closes and close_times_ms must have the same length")

    bucket_ms = _timeframe_to_ms(fixed_timeframe)

    bucket_ids: List[int] = []
    bucket_closes: List[float] = []
    bucket_index: Dict[int, int] = {}

    for close_time_ms, close in zip(close_times_ms, closes):
        bucket = int(close_time_ms) // bucket_ms
        if bucket in bucket_index:
            bucket_closes[bucket_index[bucket]] = close
        else:
            bucket_index[bucket] = len(bucket_ids)
            bucket_ids.append(bucket)
            bucket_closes.append(close)

    fast_htf = _ema(bucket_closes, ema_fast_len)
    slow_htf = _ema(bucket_closes, ema_slow_len)

    prev_fast_by_bucket: Dict[int, Optional[float]] = {}
    prev_slow_by_bucket: Dict[int, Optional[float]] = {}
    for idx, bucket in enumerate(bucket_ids):
        prev_fast_by_bucket[bucket] = fast_htf[idx - 1] if idx > 0 else None
        prev_slow_by_bucket[bucket] = slow_htf[idx - 1] if idx > 0 else None

    fast = [prev_fast_by_bucket[int(close_time_ms) // bucket_ms] for close_time_ms in close_times_ms]
    slow = [prev_slow_by_bucket[int(close_time_ms) // bucket_ms] for close_time_ms in close_times_ms]

    if xsmooth > 1:
        fast = _ema_optional(fast, xsmooth)
        slow = _ema_optional(slow, xsmooth)

    return fast, slow


def _zone_name(
    green: bool,
    blue: bool,
    lblue: bool,
    red: bool,
    orange: bool,
    yellow: bool,
) -> CdcZone:
    if green:
        return "GREEN"
    if blue:
        return "BLUE"
    if lblue:
        return "LBLUE"
    if red:
        return "RED"
    if orange:
        return "ORANGE"
    if yellow:
        return "YELLOW"
    return "NEUTRAL"


def _cdc_action_zone_series(
    closes: List[float],
    ema_fast_len: int = 12,
    ema_slow_len: int = 26,
    xsmooth: int = 1,
    close_times_ms: Optional[List[int]] = None,
    fixed_timeframe: Optional[str] = None,
) -> CdcSeries:
    n = len(closes)
    xprice = _ema(closes, xsmooth) if xsmooth > 1 else closes[:]

    if fixed_timeframe:
        if close_times_ms is None:
            raise ValueError("close_times_ms is required when fixed_timeframe is used")
        fast, slow = _fixed_tf_ma_series(
            closes,
            close_times_ms,
            ema_fast_len,
            ema_slow_len,
            xsmooth,
            fixed_timeframe,
        )
    else:
        fast = _ema(xprice, ema_fast_len)
        slow = _ema(xprice, ema_slow_len)

    bull = [
        fast[i] is not None and slow[i] is not None and fast[i] > slow[i]
        for i in range(n)
    ]
    bear = [
        fast[i] is not None and slow[i] is not None and fast[i] < slow[i]
        for i in range(n)
    ]

    green = [
        bull[i] and fast[i] is not None and xprice[i] > fast[i]
        for i in range(n)
    ]
    blue = [
        bear[i] and fast[i] is not None and slow[i] is not None and xprice[i] > fast[i] and xprice[i] > slow[i]
        for i in range(n)
    ]
    lblue = [
        bear[i] and fast[i] is not None and slow[i] is not None and xprice[i] > fast[i] and xprice[i] < slow[i]
        for i in range(n)
    ]
    red = [
        bear[i] and fast[i] is not None and xprice[i] < fast[i]
        for i in range(n)
    ]
    orange = [
        bull[i] and fast[i] is not None and slow[i] is not None and xprice[i] < fast[i] and xprice[i] < slow[i]
        for i in range(n)
    ]
    yellow = [
        bull[i] and fast[i] is not None and slow[i] is not None and xprice[i] < fast[i] and xprice[i] > slow[i]
        for i in range(n)
    ]
    zones = [
        _zone_name(green[i], blue[i], lblue[i], red[i], orange[i], yellow[i])
        for i in range(n)
    ]

    buycond = [False] * n
    sellcond = [False] * n
    for i in range(1, n):
        buycond[i] = green[i] and (not green[i - 1])
        sellcond[i] = red[i] and (not red[i - 1])

    bs_buy = _barssince(buycond)
    bs_sell = _barssince(sellcond)

    bullish = [bs_buy[i] < bs_sell[i] for i in range(n)]
    bearish = [bs_sell[i] < bs_buy[i] for i in range(n)]

    buy = [False] * n
    sell = [False] * n
    for i in range(1, n):
        buy[i] = bearish[i - 1] and buycond[i]
        sell[i] = bullish[i - 1] and sellcond[i]

    return CdcSeries(
        xprice=xprice,
        fast=fast,
        slow=slow,
        bull=bull,
        bear=bear,
        green=green,
        blue=blue,
        lblue=lblue,
        red=red,
        orange=orange,
        yellow=yellow,
        buycond=buycond,
        sellcond=sellcond,
        bullish=bullish,
        bearish=bearish,
        buy=buy,
        sell=sell,
        zones=zones,
    )


def _cdc_action_zone_direction(
    closes: List[float],
    ema_fast_len: int = 12,
    ema_slow_len: int = 26,
    xsmooth: int = 1,
    close_times_ms: Optional[List[int]] = None,
    fixed_timeframe: Optional[str] = None,
) -> Optional[Direction]:
    """
    ให้เหมือน Pine CDC ActionZone:
    - xPrice = EMA(close, xsmooth)
    - FastMA = EMA(xPrice, 12)
    - SlowMA = EMA(xPrice, 26)
    - Green = Bull and xPrice > FastMA
    - Red   = Bear and xPrice < FastMA
    - buycond  = Green and Green[1] == 0  (first green)
    - sellcond = Red   and Red[1] == 0    (first red)
    - bullish/bearish ด้วย barssince
    - buy  = bearish[1] and buycond
    - sell = bullish[1] and sellcond
    """
    n = len(closes)
    if n < max(ema_fast_len, ema_slow_len) + 5:
        return None

    series = _cdc_action_zone_series(
        closes,
        ema_fast_len=ema_fast_len,
        ema_slow_len=ema_slow_len,
        xsmooth=xsmooth,
        close_times_ms=close_times_ms,
        fixed_timeframe=fixed_timeframe,
    )
    buy = series.buy[-1]
    sell = series.sell[-1]

    if buy:
        return "LONG"
    if sell:
        return "SHORT"
    return None


def _default_risk_levels(
    direction: Direction,
    entry: float,
    atr: float,
    sl_atr_mult: float = 1.5,
    tp1_rr: float = 1.0,
    tp2_rr: float = 2.0,
    tp3_rr: float = 3.0,
) -> Dict[str, float]:
    """
    Risk แบบตรง ๆ:
    - SL = entry ± (ATR * mult)
    - TP = entry ± (distance_to_sl * RR)
    """
    if atr <= 0:
        raise ValueError("ATR must be > 0")

    if direction == "LONG":
        sl = entry - (atr * sl_atr_mult)
        risk = entry - sl
        tp1 = entry + risk * tp1_rr
        tp2 = entry + risk * tp2_rr
        tp3 = entry + risk * tp3_rr
    else:
        sl = entry + (atr * sl_atr_mult)
        risk = sl - entry
        tp1 = entry - risk * tp1_rr
        tp2 = entry - risk * tp2_rr
        tp3 = entry - risk * tp3_rr

    return {"sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3}


def analyze_candles_for_signal(
    symbol: str,
    timeframe: str,
    candles: List[Dict],
    fixed_timeframe: Optional[str] = None,
) -> Optional[SignalPayload]:
    """
    Input: candles = list of dicts from binance_client.candles_to_dicts()
    Output: SignalPayload หรือ None
    """
    if len(candles) < 60:
        return None

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    close_times_ms = [int(c["close_time_ms"]) for c in candles]

    series = _cdc_action_zone_series(
        closes,
        xsmooth=1,
        close_times_ms=close_times_ms,
        fixed_timeframe=fixed_timeframe,
    )
    direction = None
    if series.buy[-1]:
        direction = "LONG"
    elif series.sell[-1]:
        direction = "SHORT"
    if not direction:
        return None

    atrs = _atr(highs, lows, closes, length=14)
    atr_now = float(atrs[-1]) if atrs else 0.0
    if atr_now <= 0:
        return None

    entry = float(closes[-1])
    risk = _default_risk_levels(direction, entry, atr_now)

    zone = series.zones[-1]
    reason = f"CDC({direction},{zone}) + ATR14={atr_now:.4f}"
    return SignalPayload(
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        entry_price=entry,
        stop_loss=float(risk["sl"]),
        tp1=float(risk["tp1"]),
        tp2=float(risk["tp2"]),
        tp3=float(risk["tp3"]),
        reason=reason,
        zone=zone,
    )
