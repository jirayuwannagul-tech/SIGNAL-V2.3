import pytest
from unittest.mock import patch, MagicMock, call
from app_v23.core.indicator_engine import SignalPayload


def _sig(symbol="BTCUSDT", direction="LONG"):
    e = 100.0
    return SignalPayload(
        symbol=symbol, timeframe="1d", direction=direction,
        entry_price=e, stop_loss=e*0.95, tp1=e*1.05,
        tp2=e*1.10, tp3=e*1.15, reason="TEST"
    )


def _mock_svc():
    svc = MagicMock()
    sheets = MagicMock()
    values = MagicMock()
    svc.spreadsheets.return_value = sheets
    sheets.values.return_value = values
    values.append.return_value.execute.return_value = {}
    values.update.return_value.execute.return_value = {}
    values.get.return_value.execute.return_value = {"values": []}
    return svc


class TestAppendSignalRow:
    def test_calls_append(self):
        from app_v23.services.sheets_logger import append_signal_row, _reset_svc
        _reset_svc()
        svc = _mock_svc()
        with patch("app_v23.services.sheets_logger._svc", return_value=(svc, "SHEET_ID")):
            append_signal_row(_sig(), sheet_name="Signals")
        assert svc.spreadsheets().values().append.called

    def test_row_contains_symbol(self):
        from app_v23.services.sheets_logger import append_signal_row, _reset_svc
        _reset_svc()
        svc = _mock_svc()
        captured = {}
        def fake_append(**kwargs):
            captured["body"] = kwargs.get("body", {})
            return MagicMock(execute=MagicMock(return_value={}))
        svc.spreadsheets().values().append = fake_append
        with patch("app_v23.services.sheets_logger._svc", return_value=(svc, "SHEET_ID")):
            append_signal_row(_sig("ETHUSDT"), sheet_name="Signals")
        row = captured["body"]["values"][0]
        assert "ETHUSDT" in row

    def test_row_length(self):
        from app_v23.services.sheets_logger import append_signal_row, _reset_svc
        _reset_svc()
        svc = _mock_svc()
        captured = {}
        def fake_append(**kwargs):
            captured["body"] = kwargs.get("body", {})
            return MagicMock(execute=MagicMock(return_value={}))
        svc.spreadsheets().values().append = fake_append
        with patch("app_v23.services.sheets_logger._svc", return_value=(svc, "SHEET_ID")):
            append_signal_row(_sig(), sheet_name="Signals")
        row = captured["body"]["values"][0]
        assert len(row) == 15


class TestUpdateHitStatus:
    def test_no_row_found_returns_false(self):
        from app_v23.services.sheets_logger import update_hit_status, _reset_svc
        _reset_svc()
        svc = _mock_svc()
        svc.spreadsheets().values().get.return_value.execute.return_value = {"values": []}
        with patch("app_v23.services.sheets_logger._svc", return_value=(svc, "SHEET_ID")):
            result = update_hit_status("Signals", "BTCUSDT", "1d", "LONG",
                                       True, False, False, False, "ACTIVE")
        assert result is False

    def test_row_found_returns_true(self):
        from app_v23.services.sheets_logger import update_hit_status, _reset_svc
        _reset_svc()
        svc = _mock_svc()
        fake_rows = [
            ["B", "symbol", "tf", "dir"],  # header row idx=0 → skip
            ["BTCUSDT", "1d", "LONG", "e", "sl", "tp1", "tp2", "tp3",
             "", "F", "F", "F", "ACTIVE", "reason"],
        ]
        svc.spreadsheets().values().get.return_value.execute.return_value = {"values": fake_rows}
        with patch("app_v23.services.sheets_logger._svc", return_value=(svc, "SHEET_ID")):
            result = update_hit_status("Signals", "BTCUSDT", "1d", "LONG",
                                       True, True, False, False, "ACTIVE")
        assert result is True


class TestAppendDailySummaryRow:
    def test_calls_append(self):
        from app_v23.services.sheets_logger import append_daily_summary_row, _reset_svc
        _reset_svc()
        svc = _mock_svc()
        with patch("app_v23.services.sheets_logger._svc", return_value=(svc, "SHEET_ID")):
            append_daily_summary_row(
                {"date": "2026-03-07", "scanned_today": 10, "signals_today": 3, "active_positions": 1},
                sheet_name="Daily"
            )
        assert svc.spreadsheets().values().append.called
