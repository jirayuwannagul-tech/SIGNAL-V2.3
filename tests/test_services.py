import json, pytest
from unittest.mock import patch, MagicMock
from app_v23.services.binance_client import Candle, candles_to_dicts, fetch_ohlcv, fetch_last_price

class TestCandles:
    def test_to_dicts(self):
        c = Candle(1700000000000,100.,105.,98.,102.,1000.,1700086399999)
        d = candles_to_dicts([c])[0]
        assert d["close"] == pytest.approx(102.); assert d["high"] == pytest.approx(105.)
    def test_empty(self): assert candles_to_dicts([]) == []
    def test_fetch_mock(self):
        row = [1700000000000,"100.","105.","98.","102.","1000.",1700086399999,"0",0,"0","0","0"]
        m = MagicMock(); m.json.return_value=[row]; m.raise_for_status=MagicMock()
        with patch("requests.get", return_value=m):
            cs = fetch_ohlcv("BTCUSDT","1d",1)
        assert cs[0].close == pytest.approx(102.)
    def test_last_price_mock(self):
        m = MagicMock(); m.json.return_value={"price":"95000.5"}; m.raise_for_status=MagicMock()
        with patch("requests.get", return_value=m):
            assert fetch_last_price("BTCUSDT") == pytest.approx(95000.5)
    def test_fetch_raises(self):
        import requests as req
        m = MagicMock(); m.raise_for_status.side_effect=req.HTTPError("404")
        with patch("requests.get", return_value=m):
            with pytest.raises(RuntimeError): fetch_ohlcv("X","1d",1)

class TestDailyReporter:
    @pytest.fixture(autouse=True)
    def patch_paths(self, tmp_path):
        with patch("app_v23.services.daily_reporter._STATS_FILE", tmp_path/"s.json"), \
             patch("app_v23.services.daily_reporter._POSITIONS_FILE", tmp_path/"p.json"), \
             patch("app_v23.services.daily_reporter._DATA_DIR", tmp_path): yield
    def test_default_zeros(self):
        from app_v23.services.daily_reporter import load_stats_for_today
        s = load_stats_for_today(); assert s.scanned==0; assert s.signals==0
    def test_record_scan(self):
        from app_v23.services.daily_reporter import record_scan, load_stats_for_today
        record_scan(10); record_scan(5); assert load_stats_for_today().scanned==15
    def test_record_signal(self):
        from app_v23.services.daily_reporter import record_signal, load_stats_for_today
        record_signal(); record_signal(); assert load_stats_for_today().signals==2
    def test_message_keywords(self):
        from app_v23.services.daily_reporter import format_daily_summary_message
        m = format_daily_summary_message()
        assert "DAILY SUMMARY" in m; assert "Scanned" in m; assert "Signals" in m
    def test_payload_structure(self):
        from app_v23.services.daily_reporter import get_daily_summary_payload, record_scan
        record_scan(20); p = get_daily_summary_payload()
        assert "date" in p; assert p["scanned_today"]==20
