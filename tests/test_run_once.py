import pytest
from unittest.mock import patch
from tests.conftest import make_candles
from app_v23.run_once import run_once, RC_SUCCESS, RC_SKIP, RC_INVALID_INPUT
from app_v23.services.binance_client import Candle

def _dicts(n=120, trend=0.5):
    return make_candles(n=n, trend=trend)

def _objs(n=120, trend=0.5):
    return [Candle(int(d["open_time_ms"]),float(d["open"]),float(d["high"]),
                   float(d["low"]),float(d["close"]),float(d["volume"]),int(d["close_time_ms"]))
            for d in _dicts(n, trend)]

def _old_dicts(n=120):
    dicts = _dicts(n)
    old = 1_600_000_000_000
    for i, d in enumerate(dicts):
        d["close_time_ms"] = old + i * 86_400_000
    return dicts


class TestTimeframe:
    def test_4h_invalid(self):  assert run_once("BTCUSDT", "4h")  == RC_INVALID_INPUT
    def test_15m_invalid(self): assert run_once("BTCUSDT", "15m") == RC_INVALID_INPUT


class TestAlreadyEmitted:
    @patch("app_v23.run_once.is_locked", return_value=False)
    @patch("app_v23.run_once.get_last_emitted_close_time_ms")
    @patch("app_v23.run_once.candles_to_dicts")
    @patch("app_v23.run_once.fetch_ohlcv")
    def test_skip(self, mock_fetch, mock_dicts, mock_emitted, mock_locked):
        d = _old_dicts()
        ts = int(d[-1]["close_time_ms"])
        mock_fetch.return_value = _objs()
        mock_dicts.return_value = d
        mock_emitted.return_value = ts
        assert run_once("BTCUSDT", "1d") == RC_SKIP


class TestNoSignal:
    @patch("app_v23.run_once.analyze_candles_for_signal", return_value=None)
    @patch("app_v23.run_once.is_locked", return_value=False)
    @patch("app_v23.run_once.get_last_emitted_close_time_ms", return_value=0)
    @patch("app_v23.run_once.candles_to_dicts")
    @patch("app_v23.run_once.fetch_ohlcv")
    def test_skip(self, mock_fetch, mock_dicts, mock_emitted, mock_locked, mock_sig):
        mock_fetch.return_value = _objs()
        mock_dicts.return_value = _old_dicts()
        assert run_once("BTCUSDT", "1d") == RC_SKIP


class TestSuccess:
    @patch("app_v23.run_once.set_last_emitted_close_time_ms")
    @patch("app_v23.run_once.create_position")
    @patch("app_v23.services.dispatcher.send_telegram_text")  # ✅ mock ที่ระดับ network call
    @patch("app_v23.run_once.is_locked", return_value=False)
    @patch("app_v23.run_once.get_last_emitted_close_time_ms", return_value=0)
    @patch("app_v23.run_once.candles_to_dicts")
    @patch("app_v23.run_once.fetch_ohlcv")
    def test_dispatches(self, mock_fetch, mock_dicts, mock_emitted, mock_locked,
                        mock_tg, mock_create, mock_set):
        from app_v23.core.indicator_engine import SignalPayload
        fake = SignalPayload("BTCUSDT","1d","LONG",100.,95.,105.,110.,115.,"TEST")
        mock_fetch.return_value = _objs()
        mock_dicts.return_value = _old_dicts()
        with patch("app_v23.run_once.analyze_candles_for_signal", return_value=fake):
            rc = run_once("BTCUSDT", "1d")
        assert rc == RC_SUCCESS
        mock_tg.assert_called_once()   # Telegram ถูกเรียก
        mock_create.assert_called_once()
        mock_set.assert_called_once()
