import threading
from datetime import datetime

import pytest

from orion.trading import (autopilot, backtest, data, demo, exchange, journal, lab, market, practice, risk, settings,
                           signals, watcher)
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
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "demo.json")
    monkeypatch.setattr(practice, "PRACTICE", tmp_path / "practice.json")
    monkeypatch.setattr(lab, "LAB", tmp_path / "lab.json")
    settings.set_enabled(True)                       # REAL TRADE on — the real alerts are tested here
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
    w.scan()
    world["BTC"] = [sig(2)]
    w.scan()
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
    assert journal.record(days=1)["open"] == 2


def test_at_night_only_the_journal(world):
    w, said, hud = make(hour=2)
    world["BTC"] = [sig(1)]
    w.scan()
    assert said == [] and hud[0][0] == "addLog"


def test_real_alerts_need_real_trade(world):
    settings.set_enabled(False)
    w, said, hud = make()
    world["BTC"] = [sig(1)]
    w.scan()
    assert said == [] and hud == [] and journal.record(days=1)["open"] == 1


def test_positions_chip_fills_and_time_stop(world, monkeypatch):
    w, said, hud = make()
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    monkeypatch.setattr(autopilot, "guard", lambda network, account: [])
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
        {"coin": "BTC", "side": "long", "pnl_usd": 5.0, "pnl_pct": 1.0}], "demo": []},)) in hud
    assert [s for s in said if "Етериум" in s] == ["Сър, позицията в Етериум се затвори на 1 901 — +5.00 долара."]
    assert sum("48 часа" in s for s in said) == 1
    w.positions()
    assert sum("48 часа" in s for s in said) == 1
    assert sum("Етериум" in s for s in said) == 1


def test_no_key_and_no_demo_hides_the_chip(world):
    w, said, hud = make()
    w.positions()
    assert hud == [("setTrading", (None,))]


def test_the_chip_shows_the_demo_accounts_without_a_key(world):
    settings.set_demo(True)
    demo.create("", 1000)
    w, said, hud = make()
    w.positions()
    assert hud == [("setTrading", ({"network": None, "positions": [], "demo": [{"name": "демо 1", "pct": 0.0}]},))]


def test_demo_and_practice_run_only_with_demo_test_on(world, monkeypatch):
    calls = []
    monkeypatch.setattr(demo, "step", lambda book, prepared, report: (
        calls.append(("demo", sorted(prepared))), ["DEMO демо 1: отворих лонг на биткойн."])[1])
    monkeypatch.setattr(practice, "step", lambda prepared: calls.append(("practice", sorted(prepared))))
    w, said, hud = make()
    w.scan()
    assert calls == []
    settings.set_demo(True)
    w.scan()
    assert calls == [("demo", ["BTC", "ETH", "SOL"]), ("practice", ["BTC", "ETH", "SOL"])]
    assert ("addLog", ("trading", "DEMO демо 1: отворих лонг на биткойн.")) in hud and said == []


def test_tick_runs_each_job_on_its_own_schedule(world, monkeypatch):
    w, said, hud = make()
    calls = []
    monkeypatch.setattr(w, "scan", lambda: calls.append("scan"))
    monkeypatch.setattr(w, "positions", lambda: calls.append("positions"))
    monkeypatch.setattr(journal, "resolve", lambda bars_for=None: calls.append("resolve"))
    w.tick()
    assert calls == ["positions", "scan", "resolve"]
    calls.clear()
    w.clock.now += 120
    w.tick()
    assert calls == []
    w.clock.now += 15 * 60
    w.tick()
    assert calls == ["positions", "scan"]


def test_the_lab_search_and_the_testnet_check_run_without_the_lock(world, monkeypatch):
    settings.set_demo(True)
    w, said, hud = make()
    monkeypatch.setattr(w, "scan", lambda: None)
    monkeypatch.setattr(w, "positions", lambda: None)
    monkeypatch.setattr(journal, "resolve", lambda bars_for=None: None)
    held, marked = [], []
    monkeypatch.setattr(lab, "due", lambda: "breakout")
    monkeypatch.setattr(market, "history", lambda coin, params=None: coin)
    monkeypatch.setattr(lab, "search", lambda strategy, markets: (held.append(("search", w.lock.locked())), None)[1])
    monkeypatch.setattr(lab, "start", lambda strategy, found, log=print: (
        held.append(("start", w.lock.locked())), "пробвам нови числа")[1])
    monkeypatch.setattr(practice, "testnet_due", lambda: True)
    monkeypatch.setattr(practice, "mark_testnet", lambda: marked.append(w.lock.locked()))
    monkeypatch.setattr(exchange, "testnet_check", lambda: (held.append(("testnet", w.lock.locked())),
                                                            "Проверката мина.")[1])
    w.tick()
    assert held == [("search", False), ("start", True), ("testnet", False)] and marked == [True]
    assert ("addLog", ("trading", "Лаборатория: пробвам нови числа.")) in hud
    assert ("addLog", ("trading", "Проверката мина.")) in hud


# --- The autopilot (REAL TRADE with a key) ---------------------------------------------------------
def test_with_a_key_the_autopilot_trades_instead_of_the_alert(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    calls = []
    monkeypatch.setattr(autopilot, "step", lambda prepared, report, network: (
        calls.append((sorted(prepared), report, network)),
        [("Отворих лонг на биткойн — пробив.", True), ("Пропуснах сигнал за шорт на етериум.", False)])[1])
    w, said, hud = make()
    world["BTC"] = [sig(1)]
    w.scan()
    assert calls == [(["BTC", "ETH", "SOL"], REPORT, "testnet")]
    assert said == ["Отворих лонг на биткойн — пробив."]
    assert ("addLog", ("trading", "Пропуснах сигнал за шорт на етериум.")) in hud
    assert journal.record(days=1)["open"] == 1                 # the signal is still in the journal


def test_no_autopilot_while_real_trade_is_off_or_in_test_mode(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    monkeypatch.setattr(autopilot, "step", lambda *args: pytest.fail("no autopilot"))
    monkeypatch.setattr(exchange, "blocked", True)
    make()[0].scan()
    monkeypatch.setattr(exchange, "blocked", False)
    settings.set_enabled(False)
    make()[0].scan()


def test_the_guard_runs_at_every_position_check_while_real_trade_is_on(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    state = risk.AccountState(1000.0)
    monkeypatch.setattr(exchange, "account_state", lambda network: (state, {}))
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [])
    seen = []
    monkeypatch.setattr(autopilot, "guard", lambda network, account: (
        seen.append((network, account)), [("Затварям лонг на биткойн — изтекоха 48 часа.", True)])[1])
    w, said, hud = make()
    w.positions()
    assert seen == [("testnet", state)] and said == ["Затварям лонг на биткойн — изтекоха 48 часа."]
    settings.set_enabled(False)
    w.positions()
    assert len(seen) == 1


def test_the_48_hour_reminder_is_only_for_sirs_own_trades(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    monkeypatch.setattr(autopilot, "guard", lambda network, account: [])
    state = risk.AccountState(1000.0, {"BTC": {"side": "long", "size": 0.01, "entry": 84000.0, "pnl": 0.0,
                                               "liq": 0.0, "value": 840.0}})
    monkeypatch.setattr(exchange, "account_state", lambda network: (state, {}))
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [])
    w, said, hud = make()
    monkeypatch.setattr(journal, "_now", lambda: int(w.clock.now * 1000))
    plan = risk.OrderPlan("BTC", "long", 0.01, 84000.0, 83000.0, 86000.0, 2, 840.0, 420.0, 10.0, 20.0, 0.0, 0.8,
                          "testnet")
    journal.add_trade(plan, "пробив", auto=True)
    w.clock.now += 49 * 3600
    w.positions()
    assert not any("48 часа" in s for s in said)


def test_an_old_close_is_not_replayed_over_a_trade_that_is_open_again(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    monkeypatch.setattr(autopilot, "guard", lambda network, account: [])
    position = {"side": "long", "size": 0.01, "entry": 100.0, "pnl": 0.0, "liq": 0.0, "value": 1.0}
    state = risk.AccountState(1000.0, {"BTC": dict(position), "ETH": dict(position)})
    monkeypatch.setattr(exchange, "account_state", lambda network: (state, {}))
    start_ms = int(Clock(10).now * 1000)                   # make() below uses the same Clock(10)
    fills = [{"coin": "BTC", "dir": "Close Long", "px": "95", "closedPnl": "-5", "time": start_ms - 10 * 3_600_000}]
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [f for f in fills if f["time"] >= since])
    for coin, hours_ago in (("ETH", 30), ("BTC", 2)):
        monkeypatch.setattr(journal, "_now", lambda h=hours_ago: start_ms - h * 3_600_000)
        journal.add_trade(risk.OrderPlan(coin, "long", 0.01, 100.0, 98.0, 104.0, 2, 1.0, 0.5, 0.02, 0.04, 50.0,
                                         0.001, "testnet"), "пробив", auto=True)
    w, said, hud = make()                                  # Orion starts after both trades were opened
    w.positions()
    assert not any("се затвори" in s for s in said)
    assert sorted(t["coin"] for t in journal.open_trades()) == ["BTC", "ETH"]


def test_no_guard_in_test_mode(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    monkeypatch.setattr(exchange, "account_state", lambda network: (risk.AccountState(1000.0), {}))
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [])
    monkeypatch.setattr(exchange, "blocked", True)
    monkeypatch.setattr(autopilot, "guard", lambda *args: pytest.fail("no guard in test mode"))
    make()[0].positions()


def test_the_48_hour_reminder_covers_autopilot_trades_while_real_trade_is_off(world, monkeypatch):
    settings.set_enabled(False)
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    monkeypatch.setattr(autopilot, "guard", lambda *args: pytest.fail("no guard while REAL TRADE is off"))
    state = risk.AccountState(1000.0, {"BTC": {"side": "long", "size": 0.01, "entry": 84000.0, "pnl": 0.0,
                                               "liq": 0.0, "value": 840.0}})
    monkeypatch.setattr(exchange, "account_state", lambda network: (state, {}))
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [])
    w, said, hud = make()
    monkeypatch.setattr(journal, "_now", lambda: int(w.clock.now * 1000))
    plan = risk.OrderPlan("BTC", "long", 0.01, 84000.0, 83000.0, 86000.0, 2, 840.0, 420.0, 10.0, 20.0, 0.0, 0.8,
                          "testnet")
    journal.add_trade(plan, "пробив", auto=True)
    w.clock.now += 49 * 3600
    w.positions()
    assert sum("48 часа" in s for s in said) == 1
