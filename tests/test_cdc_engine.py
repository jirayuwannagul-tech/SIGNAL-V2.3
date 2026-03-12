"""
test CDC ActionZone logic โดยละเอียด
"""
import pytest

from app_v23.core.indicator_engine import (
    _barssince,
    _cdc_action_zone_direction,
    _cdc_action_zone_series,
    _ema,
)


def _ema_ref(values, length):
    if length <= 0:
        raise ValueError("EMA length must be > 0")
    if not values:
        return []
    k = 2 / (length + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append((value * k) + (out[-1] * (1 - k)))
    return out


def _ema_optional_ref(values, length):
    if length <= 0:
        raise ValueError("EMA length must be > 0")
    if not values:
        return []
    k = 2 / (length + 1)
    out = []
    prev = None
    for value in values:
        if value is None:
            out.append(prev)
            continue
        prev = value if prev is None else (value * k) + (prev * (1 - k))
        out.append(prev)
    return out


def _barssince_ref(cond):
    out = []
    last_true = None
    for idx, value in enumerate(cond):
        if value:
            last_true = idx
            out.append(0)
        else:
            out.append(idx - last_true if last_true is not None else 10**9)
    return out


def _timeframe_to_ms_ref(timeframe):
    tf = timeframe.strip()
    aliases = {"D": 86_400_000, "W": 604_800_000, "M": 2_592_000_000}
    if tf.upper() in aliases:
        return aliases[tf.upper()]
    if tf.isdigit():
        return int(tf) * 60_000
    qty = int(tf[:-1])
    unit = tf[-1].lower()
    if unit == "m":
        return qty * 60_000
    if unit == "h":
        return qty * 3_600_000
    if unit == "d":
        return qty * 86_400_000
    if unit == "w":
        return qty * 604_800_000
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _fixed_tf_ma_series_ref(closes, close_times_ms, ema_fast_len, ema_slow_len, xsmooth, fixed_timeframe):
    bucket_ms = _timeframe_to_ms_ref(fixed_timeframe)
    bucket_ids = []
    bucket_closes = []
    bucket_index = {}

    for close_time_ms, close in zip(close_times_ms, closes):
        bucket = int(close_time_ms) // bucket_ms
        if bucket in bucket_index:
            bucket_closes[bucket_index[bucket]] = close
        else:
            bucket_index[bucket] = len(bucket_ids)
            bucket_ids.append(bucket)
            bucket_closes.append(close)

    fast_htf = _ema_ref(bucket_closes, ema_fast_len)
    slow_htf = _ema_ref(bucket_closes, ema_slow_len)

    prev_fast_by_bucket = {}
    prev_slow_by_bucket = {}
    for idx, bucket in enumerate(bucket_ids):
        prev_fast_by_bucket[bucket] = fast_htf[idx - 1] if idx > 0 else None
        prev_slow_by_bucket[bucket] = slow_htf[idx - 1] if idx > 0 else None

    fast = [prev_fast_by_bucket[int(close_time_ms) // bucket_ms] for close_time_ms in close_times_ms]
    slow = [prev_slow_by_bucket[int(close_time_ms) // bucket_ms] for close_time_ms in close_times_ms]
    if xsmooth > 1:
        fast = _ema_optional_ref(fast, xsmooth)
        slow = _ema_optional_ref(slow, xsmooth)
    return fast, slow


def _cdc_reference(closes, close_times_ms=None, ema_fast_len=12, ema_slow_len=26, xsmooth=1, fixed_timeframe=None):
    n = len(closes)
    xprice = _ema_ref(closes, xsmooth) if xsmooth > 1 else closes[:]

    if fixed_timeframe:
        fast, slow = _fixed_tf_ma_series_ref(
            closes,
            close_times_ms,
            ema_fast_len,
            ema_slow_len,
            xsmooth,
            fixed_timeframe,
        )
    else:
        fast = _ema_ref(xprice, ema_fast_len)
        slow = _ema_ref(xprice, ema_slow_len)

    bull = [fast[i] is not None and slow[i] is not None and fast[i] > slow[i] for i in range(n)]
    bear = [fast[i] is not None and slow[i] is not None and fast[i] < slow[i] for i in range(n)]

    green = [bull[i] and fast[i] is not None and xprice[i] > fast[i] for i in range(n)]
    blue = [bear[i] and fast[i] is not None and slow[i] is not None and xprice[i] > fast[i] and xprice[i] > slow[i] for i in range(n)]
    lblue = [bear[i] and fast[i] is not None and slow[i] is not None and xprice[i] > fast[i] and xprice[i] < slow[i] for i in range(n)]
    red = [bear[i] and fast[i] is not None and xprice[i] < fast[i] for i in range(n)]
    orange = [bull[i] and fast[i] is not None and slow[i] is not None and xprice[i] < fast[i] and xprice[i] < slow[i] for i in range(n)]
    yellow = [bull[i] and fast[i] is not None and slow[i] is not None and xprice[i] < fast[i] and xprice[i] > slow[i] for i in range(n)]

    zones = []
    for idx in range(n):
        if green[idx]:
            zones.append("GREEN")
        elif blue[idx]:
            zones.append("BLUE")
        elif lblue[idx]:
            zones.append("LBLUE")
        elif red[idx]:
            zones.append("RED")
        elif orange[idx]:
            zones.append("ORANGE")
        elif yellow[idx]:
            zones.append("YELLOW")
        else:
            zones.append("NEUTRAL")

    buycond = [False] * n
    sellcond = [False] * n
    for idx in range(1, n):
        buycond[idx] = green[idx] and (not green[idx - 1])
        sellcond[idx] = red[idx] and (not red[idx - 1])

    bs_buy = _barssince_ref(buycond)
    bs_sell = _barssince_ref(sellcond)
    bullish = [bs_buy[i] < bs_sell[i] for i in range(n)]
    bearish = [bs_sell[i] < bs_buy[i] for i in range(n)]

    buy = [False] * n
    sell = [False] * n
    for idx in range(1, n):
        buy[idx] = bearish[idx - 1] and buycond[idx]
        sell[idx] = bullish[idx - 1] and sellcond[idx]

    return {
        "zones": zones,
        "buy": buy,
        "sell": sell,
    }


def _close_wave():
    closes = []
    closes.extend([100.0 + i * 0.8 for i in range(24)])
    closes.extend([118.0 - i * 0.4 for i in range(12)])
    closes.extend([113.2 - i * 1.1 for i in range(16)])
    closes.extend([95.6 + i * 0.9 for i in range(14)])
    closes.extend([108.2 - i * 0.7 for i in range(12)])
    return closes


def _close_times(step_ms, count, start=1_700_000_000_000):
    return [start + (idx * step_ms) for idx in range(count)]


class TestCdcEdgeCases:
    def test_exact_min_length(self):
        c = [float(i) for i in range(35)]
        result = _cdc_action_zone_direction(c)
        assert result in (None, "LONG", "SHORT")

    def test_strong_uptrend_returns_long_or_none(self):
        c = [float(100 + i * 2) for i in range(100)]
        result = _cdc_action_zone_direction(c)
        assert result in (None, "LONG")

    def test_strong_downtrend_returns_short_or_none(self):
        c = [float(200 - i * 2) for i in range(100)]
        result = _cdc_action_zone_direction(c)
        assert result in (None, "SHORT")

    def test_flat_market_returns_none_or_signal(self):
        c = [100.0] * 100
        result = _cdc_action_zone_direction(c)
        assert result in (None, "LONG", "SHORT")

    def test_output_type(self):
        c = [float(100 + i * 0.3) for i in range(80)]
        result = _cdc_action_zone_direction(c)
        assert result is None or isinstance(result, str)

    def test_custom_params(self):
        c = [float(100 + i * 0.5) for i in range(100)]
        result = _cdc_action_zone_direction(c, ema_fast_len=5, ema_slow_len=10)
        assert result in (None, "LONG", "SHORT")

    def test_series_matches_reference_default_mode(self):
        closes = _close_wave()
        actual = _cdc_action_zone_series(closes, xsmooth=1)
        expected = _cdc_reference(closes, xsmooth=1)
        assert actual.zones == expected["zones"]
        assert actual.buy == expected["buy"]
        assert actual.sell == expected["sell"]

    def test_series_emits_all_color_zones(self):
        closes = _close_wave()
        actual = _cdc_action_zone_series(closes, xsmooth=1)
        zone_set = set(actual.zones)
        assert {"GREEN", "BLUE", "RED", "ORANGE", "YELLOW"}.issubset(zone_set)

    def test_fixed_timeframe_matches_reference(self):
        closes = _close_wave() * 2
        close_times_ms = _close_times(6 * 60 * 60 * 1000, len(closes))
        actual = _cdc_action_zone_series(
            closes,
            xsmooth=1,
            close_times_ms=close_times_ms,
            fixed_timeframe="D",
        )
        expected = _cdc_reference(
            closes,
            close_times_ms=close_times_ms,
            xsmooth=1,
            fixed_timeframe="D",
        )
        assert actual.zones == expected["zones"]
        assert actual.buy == expected["buy"]
        assert actual.sell == expected["sell"]

    def test_direction_matches_reference_in_fixed_timeframe_mode(self):
        closes = _close_wave() * 2
        close_times_ms = _close_times(6 * 60 * 60 * 1000, len(closes))
        expected = _cdc_reference(
            closes,
            close_times_ms=close_times_ms,
            xsmooth=1,
            fixed_timeframe="D",
        )
        actual = _cdc_action_zone_direction(
            closes,
            xsmooth=1,
            close_times_ms=close_times_ms,
            fixed_timeframe="D",
        )
        if expected["buy"][-1]:
            assert actual == "LONG"
        elif expected["sell"][-1]:
            assert actual == "SHORT"
        else:
            assert actual is None


class TestEmaEdgeCases:
    def test_convergence(self):
        c = [100.0] * 50
        r = _ema(c, 10)
        assert all(abs(v - 100.0) < 0.001 for v in r[20:])

    def test_large_length(self):
        r = _ema([float(i) for i in range(100)], 50)
        assert len(r) == 100

    def test_negative_values(self):
        r = _ema([-10.0, -5.0, 0.0, 5.0, 10.0], 3)
        assert len(r) == 5


class TestBarsSinceEdgeCases:
    def test_single_true(self):
        r = _barssince([True])
        assert r == [0]

    def test_single_false(self):
        r = _barssince([False])
        assert r == [10**9]

    def test_reset_after_true(self):
        r = _barssince([True, False, False, True, False])
        assert r[0] == 0
        assert r[1] == 1
        assert r[2] == 2
        assert r[3] == 0
        assert r[4] == 1
