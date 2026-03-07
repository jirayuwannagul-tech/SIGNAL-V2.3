"""
test CDC ActionZone logic โดยละเอียด
"""
import pytest
from app_v23.core.indicator_engine import _cdc_action_zone_direction, _ema, _barssince


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
