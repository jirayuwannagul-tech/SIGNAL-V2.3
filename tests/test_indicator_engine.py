import pytest
from app_v23.core.indicator_engine import (
    _ema, _atr, _barssince,
    _cdc_action_zone_direction,
    _default_risk_levels, analyze_candles_for_signal, SignalPayload,
)
from tests.conftest import make_candles

class TestEma:
    def test_single_value(self):         assert _ema([42.0], 5) == [42.0]
    def test_length_matches(self):       assert len(_ema([1.0]*5, 3)) == 5
    def test_first_equals_input(self):   assert _ema([10.0,20.0], 2)[0] == pytest.approx(10.0)
    def test_monotone_up(self):          r = _ema([float(x) for x in range(1,21)], 5); assert r[-1] > r[0]
    def test_empty(self):                assert _ema([], 5) == []
    def test_invalid_length(self):
        with pytest.raises(ValueError): _ema([1.0], 0)
    def test_length_1_returns_same(self): assert _ema([5.0,10.0,15.0], 1) == pytest.approx([5.0,10.0,15.0])

class TestAtr:
    def _data(self):
        return [10.,11.,12.,11.,13.], [9.,10.,10.,9.,10.], [9.5,10.5,11.5,10.8,12.]
    def test_length_matches(self):     h,l,c = self._data(); assert len(_atr(h,l,c,3)) == 5
    def test_all_positive(self):       h,l,c = self._data(); assert all(v>0 for v in _atr(h,l,c,3))
    def test_mismatch_raises(self):
        with pytest.raises(ValueError): _atr([1.,2.],[1.],[1.,2.],2)
    def test_empty(self):              assert _atr([],[],[],3) == []

class TestBarssince:
    def test_basic(self):
        r = _barssince([False,True,False,False,True,False])
        assert r[0]==10**9; assert r[1]==0; assert r[2]==1; assert r[4]==0; assert r[5]==1
    def test_all_false(self): assert all(v==10**9 for v in _barssince([False]*3))
    def test_all_true(self):  assert all(v==0 for v in _barssince([True]*3))
    def test_empty(self):     assert _barssince([]) == []

class TestDefaultRiskLevels:
    def test_long_sl_below(self):    assert _default_risk_levels("LONG",100.,2.)["sl"] < 100.
    def test_short_sl_above(self):   assert _default_risk_levels("SHORT",100.,2.)["sl"] > 100.
    def test_long_tps_ascending(self):
        r = _default_risk_levels("LONG",100.,2.)
        assert r["tp1"] < r["tp2"] < r["tp3"]
    def test_short_tps_descending(self):
        r = _default_risk_levels("SHORT",100.,2.)
        assert r["tp1"] > r["tp2"] > r["tp3"]
    def test_rr_correct(self):
        r = _default_risk_levels("LONG",100.,2.,sl_atr_mult=1.5,tp2_rr=2.0)
        risk = 100. - r["sl"]
        assert (r["tp2"]-100.)/risk == pytest.approx(2.0, rel=1e-6)
    def test_zero_atr_raises(self):
        with pytest.raises(ValueError): _default_risk_levels("LONG",100.,0.)

class TestCdcDirection:
    def test_too_short_none(self):   assert _cdc_action_zone_direction([100.]*10) is None
    def test_valid_output(self):
        c = [float(100+i*0.5) for i in range(100)]
        assert _cdc_action_zone_direction(c) in (None,"LONG","SHORT")

class TestAnalyzeCandles:
    def test_too_short_none(self):  assert analyze_candles_for_signal("X","1d",make_candles(30)) is None
    def test_empty_none(self):      assert analyze_candles_for_signal("X","1d",[]) is None
    def test_valid_payload(self):
        r = analyze_candles_for_signal("BTCUSDT","1d",make_candles(200,trend=1.0))
        if r:
            assert r.direction in ("LONG","SHORT")
            assert r.entry_price > 0
            if r.direction=="LONG":  assert r.stop_loss < r.entry_price
            else:                    assert r.stop_loss > r.entry_price
