import pytest
from unittest.mock import patch
from tests.conftest import make_candles
from app_v23.services.binance_client import Candle
from app_v23.run_once import run_once, RC_SUCCESS, RC_SKIP, RC_INVALID_INPUT

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]

def _make_data(n=120, trend=0.5):
    dicts = make_candles(n=n, trend=trend)
    old = 1_600_000_000_000
    for i, d in enumerate(dicts):
        d["close_time_ms"] = old + i * 86_400_000
    objs = [Candle(int(d["open_time_ms"]),float(d["open"]),float(d["high"]),
                   float(d["low"]),float(d["close"]),float(d["volume"]),int(d["close_time_ms"]))
            for d in dicts]
    return objs, dicts


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_run_once_no_crash(symbol, tmp_path):
    objs, dicts = _make_data()
    with patch("app_v23.run_once.fetch_ohlcv", return_value=objs), \
         patch("app_v23.run_once.candles_to_dicts", return_value=dicts), \
         patch("app_v23.run_once.get_last_emitted_close_time_ms", return_value=0), \
         patch("app_v23.run_once.is_locked", return_value=False), \
         patch("app_v23.run_once.analyze_candles_for_signal", return_value=None), \
         patch("app_v23.services.position_store.POSITIONS_FILE", tmp_path/"p.json"):
        rc = run_once(symbol, "1d")
        assert rc in (RC_SUCCESS, RC_SKIP, RC_INVALID_INPUT)


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_indicator_no_crash(symbol):
    from app_v23.core.indicator_engine import analyze_candles_for_signal
    result = analyze_candles_for_signal(symbol, "1d", make_candles(n=200, trend=0.5))
    assert result is None or result.direction in ("LONG", "SHORT")


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_signal_payload_valid(symbol):
    from app_v23.core.indicator_engine import analyze_candles_for_signal
    result = analyze_candles_for_signal(symbol, "1d", make_candles(n=200, trend=1.0))
    if result:
        assert result.entry_price > 0
        assert result.stop_loss > 0
        assert result.tp1 > 0 and result.tp2 > 0 and result.tp3 > 0
        assert result.symbol == symbol
        assert result.timeframe == "1d"
        if result.direction == "LONG":
            assert result.stop_loss < result.entry_price
            assert result.tp1 < result.tp2 < result.tp3
        else:
            assert result.stop_loss > result.entry_price
            assert result.tp1 > result.tp2 > result.tp3
