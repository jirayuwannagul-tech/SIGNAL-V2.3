import pytest
from unittest.mock import patch, MagicMock
from app_v23.core.indicator_engine import SignalPayload


def _sig(symbol="BTCUSDT", direction="LONG"):
    e = 100.0
    return SignalPayload(
        symbol=symbol, timeframe="1d", direction=direction,
        entry_price=e, stop_loss=e*0.95 if direction=="LONG" else e*1.05,
        tp1=e*1.05, tp2=e*1.10, tp3=e*1.15, reason="TEST"
    )


class TestFormatMessage:
    def test_contains_symbol(self):
        from app_v23.services.dispatcher import _format_tg_message
        msg = _format_tg_message(_sig("ETHUSDT"))
        assert "ETHUSDT" in msg

    def test_contains_direction(self):
        from app_v23.services.dispatcher import _format_tg_message
        msg = _format_tg_message(_sig(direction="SHORT"))
        assert "SHORT" in msg

    def test_contains_signal_v23(self):
        from app_v23.services.dispatcher import _format_tg_message
        msg = _format_tg_message(_sig())
        assert "SIGNAL V2.3" in msg

    def test_contains_entry(self):
        from app_v23.services.dispatcher import _format_tg_message
        msg = _format_tg_message(_sig())
        assert "100.0000" in msg


class TestSendTelegramText:
    def test_missing_token_raises(self):
        from app_v23.services.dispatcher import send_telegram_text
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
            with pytest.raises(RuntimeError, match="Missing"):
                send_telegram_text("hello")

    def test_sends_ok(self):
        from app_v23.services.dispatcher import send_telegram_text
        m = MagicMock()
        m.raise_for_status = MagicMock()
        with patch("requests.post", return_value=m), \
             patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"}):
            send_telegram_text("hello")
            assert m.raise_for_status.called

    def test_with_topic_id(self):
        from app_v23.services.dispatcher import send_telegram_text
        m = MagicMock()
        m.raise_for_status = MagicMock()
        with patch("requests.post", return_value=m), \
             patch.dict("os.environ", {
                 "TELEGRAM_BOT_TOKEN": "tok",
                 "TELEGRAM_CHAT_ID": "123",
                 "TOPIC_NORMAL_ID": "999",
             }):
            send_telegram_text("hello", topic_env="TOPIC_NORMAL_ID")
            call_kwargs = m.method_calls
            assert m.raise_for_status.called


class TestDispatch:
    def test_dispatch_calls_telegram_and_sheet(self):
        from app_v23.services.dispatcher import dispatch
        m_tg = MagicMock()
        m_sheet = MagicMock()
        m_record = MagicMock()
        with patch("app_v23.services.dispatcher.send_telegram", m_tg), \
             patch("app_v23.services.dispatcher.append_signal_row", m_sheet), \
             patch("app_v23.services.dispatcher.record_signal", m_record):
            dispatch(_sig())
        assert m_tg.called
        assert m_record.called

    def test_dispatch_sheet_fail_no_raise(self):
        from app_v23.services.dispatcher import dispatch
        with patch("app_v23.services.dispatcher.send_telegram"), \
             patch("app_v23.services.dispatcher.record_signal"), \
             patch("app_v23.services.dispatcher.append_signal_row", side_effect=Exception("sheet down")):
            dispatch(_sig())  # ไม่ควร raise


class TestSendDailySummary:
    def test_calls_send_telegram_text(self):
        from app_v23.services.dispatcher import send_daily_summary_to_telegram
        with patch("app_v23.services.dispatcher.send_telegram_text") as m:
            send_daily_summary_to_telegram("summary text")
            m.assert_called_once()
