import copy
import json

import pytest

from orion.trading import backtest, market, signals
from orion.trading.data import HOUR, Bars
from orion.trading.signals import DAY, Signal
from test_trading_signals import random_walk


def bars_from(rows):
    bars = Bars(HOUR)
    for k, (o, h, l, c) in enumerate(rows):
        bars.add(k * HOUR, o, h, l, c, 1.0)
    return bars


def flat(n):
    return [(100.0, 100.5, 99.5, 100.0)] * n


def test_exit_walk_target_stop_and_both_in_one_candle():
    bars = bars_from(flat(3) + [(100.0, 102.5, 99.6, 102.0)])
    assert backtest.exit_walk("long", 99.0, 102.0, bars, 1, 10 ** 12) == (3, 102.0, "цел")
    both = bars_from(flat(3) + [(100.0, 102.5, 98.9, 101.0)])
    assert backtest.exit_walk("long", 99.0, 102.0, both, 1, 10 ** 12) == (3, 99.0, "стоп")
    gap = bars_from(flat(3) + [(98.0, 98.5, 97.0, 98.0)])
    assert backtest.exit_walk("long", 99.0, 102.0, gap, 1, 10 ** 12) == (3, 98.0, "стоп")
    short = bars_from(flat(3) + [(100.0, 100.2, 97.5, 98.0)])
    assert backtest.exit_walk("short", 101.0, 98.0, short, 1, 10 ** 12) == (3, 98.0, "цел")


def test_exit_walk_time_stop_and_still_open():
    bars = bars_from(flat(120))
    k, price, why = backtest.exit_walk("long", 90.0, 110.0, bars, 61, 61 * HOUR + 48 * HOUR)
    assert (k, price, why) == (108, 100.0, "време")
    assert backtest.exit_walk("long", 90.0, 110.0, bars_from(flat(20)), 1, 10 ** 12) is None


def test_costs_in_r():
    assert backtest.result_r("BTC", "long", 100.0, 102.0, 99.0, 0.0) == pytest.approx((0.02 - 0.0013) / 0.01)
    assert backtest.result_r("SOL", "short", 100.0, 101.0, 101.0, 0.0) == pytest.approx((-0.01 - 0.0019) / 0.01)
    t = [0, HOUR, 2 * HOUR]
    v = [0.001, 0.002, 0.003]
    assert backtest.funding_cost("long", t, v, 0, 2 * HOUR) == pytest.approx(0.005)
    assert backtest.funding_cost("short", t, v, 0, 2 * HOUR) == pytest.approx(-0.005)
    assert backtest.funding_cost("long", [], [], 0, 3 * HOUR) == pytest.approx(3 * 0.0000125)


def prepared(h1):
    n = len(h1)
    return signals.Prepared("BTC", h1, Bars(4 * HOUR), Bars(DAY), copy.deepcopy(signals.DEFAULTS), [], [], {},
                            [-1] * n, [-1] * n, None, [None] * n)


def test_simulate_enters_on_the_next_open_and_charges_costs(monkeypatch):
    rows = flat(61) + [(100.0, 100.5, 99.6, 100.2), (100.2, 101.0, 99.8, 100.8), (100.8, 102.5, 100.5, 102.2)]
    rows += flat(10)
    p = prepared(bars_from(rows))
    sig = Signal("BTC", "pullback", "long", p.h1.end(60), 100.0, 99.0, 102.0, 3, ["отскок в тренда"])
    monkeypatch.setattr(signals, "signals_at", lambda p_, i, only=None: [sig] if i == 60 else [])
    trades = backtest.simulate(p, "pullback", 0, len(p.h1))
    assert len(trades) == 1
    t = trades[0]
    assert (t.entry, t.exit, t.why, t.entry_time) == (100.0, 102.0, "цел", 61 * HOUR)
    funding = 3 * 0.0000125
    assert t.r == pytest.approx((0.02 - 0.0013 - funding) / 0.01)


def test_stats_and_the_enable_rule():
    def trades(rs):
        return [backtest.Trade("BTC", "pullback", "long", 0, 0, 1, 1, 1, 1, r, "цел") for r in rs]
    st = backtest.stats(trades([2, -1, -1, 2, -1]))
    assert (st.trades, st.win_rate, st.avg_r) == (5, 0.4, pytest.approx(0.2))
    assert st.profit_factor == pytest.approx(4 / 3) and st.max_drawdown_r == pytest.approx(2.0)
    assert not st.enabled                                    # fewer than 30 trades
    assert backtest.stats(trades([2, -1] * 15)).enabled
    assert not backtest.stats(trades([2, -1, -1] * 10)).enabled  # average 0 R
    low, high = backtest.wilson(5, 10)
    assert low == pytest.approx(0.237, abs=0.01) and high == pytest.approx(0.763, abs=0.01)
    assert backtest.stats([]).trades == 0
    assert backtest.stats(trades([1] * 30)).profit_factor == 99.0     # no losses: capped, JSON-safe


def test_run_reports_out_of_sample_and_saves(monkeypatch, tmp_path):
    monkeypatch.setattr(backtest, "STATS_FILE", tmp_path / "stats.json")
    h1 = random_walk(3000)

    def history(coin, params=None):
        return signals.prepare(coin, h1, backtest.data.resample(h1, 4 * HOUR), backtest.data.resample(h1, DAY),
                               [(t, 0.00001) for t in h1.t], copy.deepcopy(signals.DEFAULTS))

    monkeypatch.setattr(market, "history", history)
    report = backtest.run(coins=("BTC",))
    entry = report["coins"]["BTC"]
    assert set(entry) == {"pullback", "breakout", "reversal", "range", "from", "to"}
    assert entry["from"] == h1.t[int(len(h1) * backtest.SPLIT)]
    assert entry["range"]["total"] > 0
    assert json.loads((tmp_path / "stats.json").read_text(encoding="utf-8")) == report
    assert backtest.load() == report and not backtest.stale()
    assert backtest.is_enabled(report, "BTC", "pullback") == backtest.Stats.from_dict(entry["pullback"]).enabled
    assert backtest.is_enabled(None, "BTC", "pullback") is False


def test_market_live_adds_btc_trend_only_for_other_coins(monkeypatch):
    h1 = random_walk(300)
    calls = []

    def live_bars(coin, interval, count=1000):
        calls.append((coin, interval))
        return h1 if interval == "1h" else backtest.data.resample(h1, 4 * HOUR if interval == "4h" else DAY)

    monkeypatch.setattr(market.data, "live_bars", live_bars)
    monkeypatch.setattr(market.data, "recent_funding", lambda coin, days=90: [])
    monkeypatch.setattr(market.data, "fear_greed", lambda: [])
    assert market.live("BTC").btc_trend is None
    assert ("BTC", "4h") in calls
    calls.clear()
    eth = market.live("ETH")
    assert eth.btc_trend is not None and ("BTC", "4h") in calls
