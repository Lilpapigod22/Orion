from types import SimpleNamespace

import pytest

from orion.trading import journal
from orion.trading.data import HOUR, Bars
from orion.trading.signals import Signal


@pytest.fixture(autouse=True)
def temp_journal(monkeypatch, tmp_path):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.json")


def sig(time=10 * HOUR, side="long"):
    return Signal("BTC", "pullback", side, time, 100.0, 99.0, 102.0, 4, ["отскок в тренда"])


def test_a_signal_is_recorded_once_whatever_the_source():
    assert journal.add_signal(sig(), "asked")
    assert not journal.add_signal(sig(), "watch")
    assert journal.add_signal(sig(time=11 * HOUR), "watch")


def candles(rows, start=10 * HOUR):
    bars = Bars(HOUR)
    for k, (o, h, l, c) in enumerate(rows):
        bars.add(start + k * HOUR, o, h, l, c, 1.0)
    return bars


def test_resolve_settles_a_target_and_expires_what_is_too_old():
    journal.add_signal(sig(), "watch")
    journal.add_signal(sig(time=1 * HOUR), "watch")          # older than the candles we get back
    bars = candles([(100.0, 100.5, 99.5, 100.2), (100.2, 102.3, 100.0, 102.0)])
    assert journal.resolve(lambda coin: bars) == 2
    summary = journal.record(days=1, now_ms=12 * HOUR)
    assert (summary["n"], summary["wins"], summary["open"]) == (1, 1, 0)
    assert summary["avg_r"] == pytest.approx((0.02 - 0.0013) / 0.01, abs=1e-3)
    assert summary["by_strategy"]["pullback"]["n"] == 1


def test_open_signals_stay_open_until_a_level_or_48h():
    journal.add_signal(sig(), "watch")
    assert journal.resolve(lambda coin: candles([(100.0, 100.5, 99.5, 100.0)])) == 0
    assert journal.record(days=1, now_ms=12 * HOUR)["open"] == 1


def test_trades_are_tracked_for_the_time_stop():
    plan = SimpleNamespace(network="testnet", coin="ETH", side="short", entry=2000.0, stop=2040.0, target=1920.0,
                           size=0.5)
    journal.add_trade(plan, "пробив")
    assert journal.open_trade_time("ETH") is not None
    journal.close_trade("ETH", 1925.0, 37.5)
    assert journal.open_trade_time("ETH") is None


def test_autopilot_trades_are_marked_and_listed_while_open():
    from orion.trading import risk
    plan = risk.OrderPlan("BTC", "long", 0.01, 100.0, 99.0, 102.0, 2, 1.0, 0.5, 0.01, 0.02, 50.0, 0.001, "mainnet")
    journal.add_trade(plan, "breakout", auto=True)
    journal.add_trade(risk.OrderPlan("ETH", "short", 0.1, 2000.0, 2050.0, 1900.0, 2, 200.0, 100.0, 5.0, 10.0,
                                     2500.0, 0.2, "mainnet"), "без сигнал")
    found = journal.open_trades()
    assert [(e["coin"], e["auto"], e["stop"]) for e in found] == [("BTC", True, 99.0), ("ETH", False, 2050.0)]
    journal.close_trade("BTC", 102.0, 2.0)
    assert [e["coin"] for e in journal.open_trades()] == ["ETH"]
