# app_v22_clean/core/indicator_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Literal


Direction = Literal["LONG", "SHORT"]


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


def _cdc_action_zone_direction(
    closes: List[float],
    ema_fast_len: int = 12,
    ema_slow_len: int = 26,
    xsmooth: int = 1,
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
    - bullish/bearish ด้วย barssince แล้วค่อยออก buy/sell
    """
    n = len(closes)
    if n < max(ema_fast_len, ema_slow_len) + 5:
        return None

    # xPrice (Pine: ta.ema(xsrc, xsmooth))
    xprice = _ema(closes, xsmooth) if xsmooth > 1 else closes[:]  # xsmooth=1 => ใช้ close ตรง ๆ
    fast = _ema(xprice, ema_fast_len)
    slow = _ema(xprice, ema_slow_len)

    bull = [f > s for f, s in zip(fast, slow)]
    bear = [f < s for f, s in zip(fast, slow)]

    green = [bull[i] and (xprice[i] > fast[i]) for i in range(n)]
    red = [bear[i] and (xprice[i] < fast[i]) for i in range(n)]

    buycond = [False] * n
    sellcond = [False] * n
    for i in range(1, n):
        buycond[i] = green[i] and (not green[i - 1])
        sellcond[i] = red[i] and (not red[i - 1])

    bs_buy = _barssince(buycond)
    bs_sell = _barssince(sellcond)

    bullish = [bs_buy[i] < bs_sell[i] for i in range(n)]
    bearish = [bs_sell[i] < bs_buy[i] for i in range(n)]

    # Pine: buy = bearish[1] and buycond ; sell = bullish[1] and sellcond
    i = n - 1
    buy = (bearish[i - 1] if i - 1 >= 0 else False) and buycond[i]
    sell = (bullish[i - 1] if i - 1 >= 0 else False) and sellcond[i]

    if buy:
        return "LONG"
    if sell:
        return "SHORT"
    return None


def _pullback_confirm(
    direction: Direction,
    highs: List[float],
    lows: List[float],
    closes: List[float],
    lookback: int = 5,
) -> bool:
    """
    Pullback confirmation (เรียบ/ตรง):
    - LONG: ใน lookback ล่าสุด ต้องมีการ "ย่อลง" (low ต่ำกว่า low ก่อนหน้า) แล้วปิดกลับขึ้น (close ล่าสุด > close ก่อนหน้า)
    - SHORT: ใน lookback ล่าสุด ต้องมีการ "เด้งขึ้น" (high สูงกว่า high ก่อนหน้า) แล้วปิดกลับลง (close ล่าสุด < close ก่อนหน้า)

    หมายเหตุ: นี่คือโครงเบื้องต้นเพื่อให้ pipeline เดินได้ก่อน
    ถ้าคุณมีนิยาม pullback แบบเดิมอยู่แล้ว เดี๋ยวเราย้ายสูตรเดิมมาทับตรงนี้
    """
    n = len(closes)
    if n < lookback + 2:
        return False

    # ใช้ 2 แท่งท้ายเป็น trigger
    c1, c2 = closes[-2], closes[-1]
    if direction == "LONG":
        # มี lower-low ในช่วง lookback
        has_pullback = any(lows[i] < lows[i - 1] for i in range(n - lookback, n))
        return has_pullback and (c2 > c1)
    else:
        has_pullback = any(highs[i] > highs[i - 1] for i in range(n - lookback, n))
        return has_pullback and (c2 < c1)


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

    direction = _cdc_action_zone_direction(closes, xsmooth=1)
    if not direction:
        return None

    if not _pullback_confirm(direction, highs, lows, closes):
        return None

    atrs = _atr(highs, lows, closes, length=14)
    atr_now = float(atrs[-1]) if atrs else 0.0
    if atr_now <= 0:
        return None

    entry = float(closes[-1])  # entry = close ล่าสุด (เรียบ ๆ ก่อน)
    risk = _default_risk_levels(direction, entry, atr_now)

    reason = f"CDC({direction}) + Pullback + ATR14={atr_now:.4f}"
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
    )