import sys
import pytest
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def make_candles(n=100, base_close=100.0, trend=0.0):
    import random
    random.seed(42)
    candles = []
    close = base_close
    t = 1_700_000_000_000
    for i in range(n):
        noise = random.uniform(-0.5, 0.5)
        close = max(1.0, close + trend + noise)
        high = close * random.uniform(1.001, 1.005)
        low  = close * random.uniform(0.995, 0.999)
        open_ = close * random.uniform(0.998, 1.002)
        candles.append({"open_time_ms":t,"open":open_,"high":high,"low":low,"close":close,"volume":random.uniform(1000,5000),"close_time_ms":t+86_400_000-1})
        t += 86_400_000
    return candles

@pytest.fixture
def bullish_candles(): return make_candles(n=120, base_close=100.0, trend=0.5)
@pytest.fixture
def bearish_candles(): return make_candles(n=120, base_close=200.0, trend=-0.5)
@pytest.fixture
def flat_candles():    return make_candles(n=120, base_close=100.0, trend=0.0)
