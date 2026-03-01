import pytest
from unittest.mock import patch
from app_v23.core.indicator_engine import SignalPayload

def _sig(symbol="BTCUSDT", direction="LONG", entry=100.0):
    sl  = entry*0.95 if direction=="LONG" else entry*1.05
    tp1 = entry*1.05 if direction=="LONG" else entry*0.95
    tp2 = entry*1.10 if direction=="LONG" else entry*0.90
    tp3 = entry*1.15 if direction=="LONG" else entry*0.85
    return SignalPayload(symbol=symbol,timeframe="1d",direction=direction,
                         entry_price=entry,stop_loss=sl,tp1=tp1,tp2=tp2,tp3=tp3,reason="TEST")

@pytest.fixture(autouse=True)
def patch_file(tmp_path):
    fake = tmp_path/"positions_clean.json"
    with patch("app_v23.services.position_store.POSITIONS_FILE", fake): yield fake

class TestIsLocked:
    def test_no_file(self):
        from app_v23.services.position_store import is_locked
        assert is_locked("BTCUSDT","1d") is False
    def test_locked_after_create(self):
        from app_v23.services.position_store import create_position, is_locked
        create_position(_sig()); assert is_locked("BTCUSDT","1d") is True
    def test_different_symbol(self):
        from app_v23.services.position_store import create_position, is_locked
        create_position(_sig("ETHUSDT")); assert is_locked("BTCUSDT","1d") is False

class TestCreatePosition:
    def test_active(self):
        from app_v23.services.position_store import create_position, load_positions
        create_position(_sig())
        assert load_positions()["positions"]["BTCUSDT::1d"]["status"] == "ACTIVE"
    def test_overwrite(self):
        from app_v23.services.position_store import create_position, load_positions
        create_position(_sig(entry=100.)); create_position(_sig(entry=200.))
        assert load_positions()["positions"]["BTCUSDT::1d"]["entry_price"] == pytest.approx(200.)

class TestUpdateOnPrice:
    def test_not_found(self):
        from app_v23.services.position_store import update_on_price
        assert update_on_price("BTCUSDT","1d",100.) == "NOT_FOUND"
    def test_long_sl_closes(self):
        from app_v23.services.position_store import create_position, update_on_price
        create_position(_sig()); assert update_on_price("BTCUSDT","1d",90.) == "CLOSED"
    def test_long_tp3_closes(self):
        from app_v23.services.position_store import create_position, update_on_price
        create_position(_sig()); assert update_on_price("BTCUSDT","1d",120.) == "CLOSED"
    def test_long_tp1_stays_active(self):
        from app_v23.services.position_store import create_position, update_on_price
        create_position(_sig()); assert update_on_price("BTCUSDT","1d",106.) == "ACTIVE"
    def test_short_sl_closes(self):
        from app_v23.services.position_store import create_position, update_on_price
        create_position(_sig(direction="SHORT")); assert update_on_price("BTCUSDT","1d",110.) == "CLOSED"
    def test_in_range_active(self):
        from app_v23.services.position_store import create_position, update_on_price
        create_position(_sig()); assert update_on_price("BTCUSDT","1d",102.) == "ACTIVE"

class TestEmission:
    def test_default_zero(self):
        from app_v23.services.position_store import get_last_emitted_close_time_ms
        assert get_last_emitted_close_time_ms("BTCUSDT","1d") == 0
    def test_set_get(self):
        from app_v23.services.position_store import set_last_emitted_close_time_ms, get_last_emitted_close_time_ms
        set_last_emitted_close_time_ms("BTCUSDT","1d",999)
        assert get_last_emitted_close_time_ms("BTCUSDT","1d") == 999
