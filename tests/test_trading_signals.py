import copy
import json
import math
import random

import pytest

from orion.trading import data, signals
from orion.trading.data import HOUR, Bars
from orion.trading.signals import DAY

BASE = 100 * DAY


def fake(n=80, coin="BTC", trend4=1, **series):
    """A Prepared with hand-made indicator values: every rule can be steered exactly."""
    h1 = Bars(HOUR, [BASE + k * HOUR for k in range(n)], [100.0] * n, [101.0] * n, [99.0] * n, [100.0] * n,
              [100.0] * n)
    h4 = Bars(4 * HOUR, [BASE - 4 * HOUR], [100.0], [100.0], [100.0], [110.0 if trend4 > 0 else 90.0], [1.0])
    s = {"fast1": [100.0] * n, "slow1": [95.0] * n,
         "fast4": [105.0 if trend4 > 0 else 95.0], "slow4": [100.0],
         "ema50d": [], "ema200d": [], "rsi4": [50.0], "atr1": [1.0] * n, "adx1": [20.0] * n,
         "vol1": [100.0] * n, "hi1": [101.0] * n, "lo1": [99.0] * n}
    s.update(series)
    return signals.Prepared(coin, h1, h4, Bars(DAY), copy.deepcopy(signals.DEFAULTS), [], [], s, [0] * n,
                            [-1] * n, None, [None] * n)


def test_pullback_long_fires_when_the_price_closes_back_above_the_fast_ema():
    p = fake()
    i = len(p.h1) - 1
    p.h1.c[i] = 101.0
    found = signals.signals_at(p, i, only="pullback")
    assert len(found) == 1
    s = found[0]
    assert (s.side, s.strategy, s.entry, s.time) == ("long", "pullback", 101.0, p.h1.end(i))
    assert s.stop == pytest.approx(98.9)          # beyond the swing low 99 (+0.1 ATR), more than 1.5 ATR
    assert s.target == pytest.approx(105.2)       # 2 × the stop distance
    assert s.strength == 1 and s.reasons == ["отскок в тренда"]


def test_no_pullback_long_against_the_4h_trend():
    p = fake(trend4=-1)
    p.h1.c[-1] = 101.0
    assert signals.signals_at(p, len(p.h1) - 1, only="pullback") == []


def test_breakout_long_needs_volume():
    p = fake(hi1=[100.5] * 80, adx1=[20.0] * 79 + [21.0])
    i = 79
    p.h1.c[i], p.h1.v[i] = 101.0, 200.0
    found = signals.signals_at(p, i, only="breakout")
    assert [(s.side, s.strategy) for s in found] == [("long", "breakout")]
    p.h1.v[i] = 120.0
    assert signals.signals_at(p, i, only="breakout") == []


def crowded_funding(p, days=40, rising=True):
    end = p.h1.end(len(p.h1) - 1)
    count = days * 24
    p.funding_t = [end - (count - k) * HOUR for k in range(count + 1)]
    p.funding_v = [(k if rising else count - k) * 1e-6 for k in range(count + 1)]


def test_reversal_short_when_the_crowd_is_long():
    p = fake(rsi4=[80.0])
    i = 79
    p.h1.c[i] = 98.0                                # closes below the previous candle's low (99)
    crowded_funding(p)
    found = signals.signals_at(p, i, only="reversal")
    assert [(s.side, s.strategy) for s in found] == [("short", "reversal")]
    assert found[0].stop == pytest.approx(101.0)   # swing high 101, capped at 3 ATR
    assert found[0].target == pytest.approx(92.0)


def test_reversal_needs_a_month_of_funding_history():
    p = fake(rsi4=[80.0])
    p.h1.c[79] = 98.0
    crowded_funding(p, days=10)
    assert signals.signals_at(p, 79, only="reversal") == []


def test_strength_counts_every_agreeing_factor():
    p = fake(coin="ETH")
    i = 79
    p.h1.c[i], p.h1.v[i] = 101.0, 150.0
    p.d1 = Bars(DAY, [BASE - DAY], [100.0], [100.0], [100.0], [120.0], [1.0])
    p.s["ema50d"], p.s["ema200d"], p.i1d = [110.0], [100.0], [0] * 80
    p.btc_trend = [1] * 80
    crowded_funding(p, rising=False)               # funding now at its lowest: nobody is crowded long
    s = signals.signals_at(p, i, only="pullback")[0]
    assert s.strength == 5
    assert len(s.reasons) == 5


def test_closed_index_never_looks_ahead():
    h1 = Bars(HOUR)
    for k in range(12):
        h1.add(k * HOUR, 1, 1, 1, 1, 1)
    h4 = data.resample(h1, 4 * HOUR)
    assert signals._closed_index(h1, h4) == [-1, -1, -1, 0, 0, 0, 0, 1, 1, 1, 1, 2]


def random_walk(n=3000, seed=7):
    rng = random.Random(seed)
    bars, price = Bars(HOUR), 100.0
    for k in range(n):
        o = price
        price *= math.exp(rng.gauss(0, 0.01))
        hi = max(o, price) * (1 + abs(rng.gauss(0, 0.003)))
        lo = min(o, price) * (1 - abs(rng.gauss(0, 0.003)))
        bars.add(data.HISTORY_START + k * HOUR, o, hi, lo, price, rng.uniform(50, 250))
    return bars


def test_prepare_on_a_random_walk_gives_consistent_signals():
    h1 = random_walk()
    funding = [(t, 0.00001) for t in h1.t]
    p = signals.prepare("BTC", h1, data.resample(h1, 4 * HOUR), data.resample(h1, DAY), funding,
                        copy.deepcopy(signals.DEFAULTS))
    found = [s for i in range(len(h1)) for s in signals.signals_at(p, i)]
    assert found, "a 3000-hour random walk should trigger at least one strategy"
    for s in found:
        if s.side == "long":
            assert s.stop < s.entry < s.target
        else:
            assert s.target < s.entry < s.stop
        assert 1 <= s.strength <= 5
        assert s.target - s.entry == pytest.approx(signals.DEFAULTS[s.strategy]["reward"] * (s.entry - s.stop))
    again = signals.with_params(p, copy.deepcopy(signals.DEFAULTS))
    assert [s.to_dict() for s in signals.signals_at(again, len(h1) - 1)] == \
        [s.to_dict() for s in signals.signals_at(p, len(h1) - 1)]


def test_context_and_the_24h_range():
    h1 = random_walk(400)
    p = signals.prepare("BTC", h1, data.resample(h1, 4 * HOUR), data.resample(h1, DAY), [],
                        copy.deepcopy(signals.DEFAULTS))
    ctx = signals.context(p)
    assert ctx.price == h1.c[-1] and ctx.low24 < ctx.price < ctx.high24
    assert ctx.funding_rank is None
    zigzag = Bars(HOUR)
    for k in range(100):
        zigzag.add(k * HOUR, 1, 1, 1, 100.0 * (1.01 if k % 2 else 1.0), 1)
    low, high = signals.range_24h(zigzag, 99)
    assert high / 101.0 == pytest.approx(math.exp(math.log(1.01) * math.sqrt(24)), rel=0.02)
    assert low / 101.0 == pytest.approx(math.exp(-math.log(1.01) * math.sqrt(24)), rel=0.02)


def test_signal_round_trip():
    s = signals.Signal("SOL", "breakout", "short", 5, 100.0, 101.0, 98.0, 3, ["пробив"])
    assert signals.Signal.from_dict(json.loads(json.dumps(s.to_dict()))) == s
    assert s.risk == 1.0


def test_params_default_then_promoted(monkeypatch, tmp_path):
    monkeypatch.setattr(signals, "PARAMS_FILE", tmp_path / "params.json")
    assert signals.load_params() == signals.DEFAULTS
    new = {**signals.DEFAULTS["pullback"], "fast": 13}
    signals.save_params("pullback", new, "тест")
    assert signals.load_params()["pullback"]["fast"] == 13
    saved = json.loads((tmp_path / "params.json").read_text(encoding="utf-8"))
    assert saved["history"][0]["old"] == signals.DEFAULTS["pullback"] and saved["history"][0]["why"] == "тест"
