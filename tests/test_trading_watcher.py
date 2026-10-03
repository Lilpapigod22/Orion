import threading
from datetime import datetime

import pytest

from orion.trading import backtest, data, exchange, journal, market, risk, settings, signals, watcher
from orion.trading.signals import Signal

GOOD = {"trades": 40, "win_rate": 0.5, "win_low": 0.35, "win_high": 0.65, "avg_r": 0.3, "profit_factor": 1.6,
        "max_drawdown_r": 5.0}
REPORT = {"time": 0, "coins": {"BTC": {"pullback": GOOD}}}


class Clock:
    def __init__(self, hour):
        self.now = datetime(2026, 10, 3, hour, 0).timestamp()

    def __call__(self):
        return self.now


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(market, "live", lambda coin, params=None: coin)
    found = {"BTC": [], "ETH": [], "SOL": []}
    monkeypatch.setattr(signals, "latest", lambda coin: found[coin])
    monkeypatch.setattr(backtest, "load", lambda: REPORT)
    monkeypatch.setattr(backtest, "stale", lambda: False)
    monkeypatch.setattr(data, "assets", lambda: {})
    monkeypatch.setattr(data, "record_open_interest", lambda found_: None)
    monkeypatch.setattr(exchange, "last_open", set())
    return found


def make(hour=10):
    said, hud = [], []
    w = watcher.Watcher(said.append, lambda fn, *args: hud.append((fn, args)), threading.Lock(), Clock(hour))
    return w, said, hud


def sig(time, strength=4, strategy="pullback"):
    return Signal("BTC", strategy, "long", time, 84000.0, 83000.0, 86000.0, strength, ["отскок в тренда"])


def test_a_strong_checked_signal_is_announced_once(world):
    w, said, hud = make()
    world["BTC"] = [sig(1)]
    w.scan()
    assert len(said) == 1 and "ЛОНГ на биткойн" in said[0]
    assert ("addLog", ("trading", said[0])) in hud
    w.scan()                                         # the same candle again
    world["BTC"] = [sig(2)]
    w.scan()                                         # a new candle, same coin and side, within 6 h
    assert len(said) == 1
    w.clock.now += 6 * 3600
    world["BTC"] = [sig(3)]
    w.scan()
    assert len(said) == 2


def test_weak_or_unchecked_signals_stay_quiet(world):
    w, said, hud = make()
    world["BTC"] = [sig(1, strength=3), sig(2, strategy="breakout")]
    w.scan()
    assert said == [] and not [h for h in hud if h[0] == "addLog"]
    assert journal.record(days=1)["open"] == 2       # still recorded for the honest record


def test_at_night_only_the_journal(world):
    w, said, hud = make(hour=2)
    world["BTC"] = [sig(1)]
    w.scan()
    assert said == [] and hud[0][0] == "addLog"


def test_positions_chip_fills_and_time_stop(world, monkeypatch):
    w, said, hud = make()
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    state = risk.AccountState(1000.0, {"BTC": {"side": "long", "size": 0.01, "entry": 84000.0, "pnl": 5.0,
                                               "liq": 0.0, "value": 500.0}})
    monkeypatch.setattr(exchange, "account_state", lambda network: (state, {}))
    fills = [{"coin": "ETH", "dir": "Close Short", "px": "1900", "closedPnl": "2", "time": 5},
             {"coin": "ETH", "dir": "Close Short", "px": "1901", "closedPnl": "3", "time": 6},
             {"coin": "BTC", "dir": "Open Long", "px": "84000", "closedPnl": "0", "time": 7}]
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [f for f in fills if f["time"] >= since])
    w.fills_from = 0
    plan = risk.OrderPlan("BTC", "long", 0.01, 84000.0, 83000.0, 86000.0, 2, 840.0, 420.0, 10.0, 20.0, 0.0, 0.8,
                          "testnet")
    monkeypatch.setattr(journal, "_now", lambda: int(w.clock.now * 1000))
    journal.add_trade(plan, "пробив")
    w.clock.now += 49 * 3600
    w.positions()
    assert ("setTrading", ({"network": "testnet", "positions": [
        {"coin": "BTC", "side": "long", "pnl_usd": 5.0, "pnl_pct": 1.0}]},)) in hud
    assert [s for s in said if "Етериум" in s] == ["Сър, позицията в Етериум се затвори на 1 901 — +5.00 долара."]
    assert sum("48 часа" in s for s in said) == 1
    w.positions()
    assert sum("48 часа" in s for s in said) == 1     # told once
    assert sum("Етериум" in s for s in said) == 1     # fills are not repeated


def test_no_key_hides_the_chip(world):
    w, said, hud = make()
    w.positions()
    assert hud == [("setTrading", (None,))]


def test_tick_runs_each_job_on_its_own_schedule(world, monkeypatch):
    w, said, hud = make()
    calls = []
    monkeypatch.setattr(w, "scan", lambda: calls.append("scan"))
    monkeypatch.setattr(w, "positions", lambda: calls.append("positions"))
    monkeypatch.setattr(journal, "resolve", lambda bars_for=None: calls.append("resolve"))
    w.tick()
    assert calls == ["scan", "positions", "resolve"]
    calls.clear()
    w.clock.now += 120
    w.tick()
    assert calls == []                               # no positions: every 5 minutes
    w.clock.now += 15 * 60
    w.tick()
    assert calls == ["scan", "positions"]
