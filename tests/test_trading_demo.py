from types import SimpleNamespace

import pytest

from orion.trading import demo, signals
from orion.trading.data import HOUR, Bars
from orion.trading.signals import Signal

GOOD = {"trades": 40, "win_rate": 0.5, "win_low": 0.35, "win_high": 0.65, "avg_r": 0.3, "profit_factor": 1.6,
        "max_drawdown_r": 5.0}


@pytest.fixture(autouse=True)
def temp_book(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "demo.json")


def sig(coin="BTC", time=10 * HOUR, strategy="breakout", side="long"):
    return Signal(coin, strategy, side, time, 100.0, 99.0, 102.0, 4, ["пробив"])


def candles(rows, start=10 * HOUR):
    bars = Bars(HOUR)
    for k, (o, h, l, c) in enumerate(rows):
        bars.add(start + k * HOUR, o, h, l, c, 1.0)
    return bars


def test_accounts_get_names_and_checked_settings():
    assert demo.create("", 1000) == "демо 1"
    assert demo.create("", 500) == "демо 2"
    assert demo.create("предпазлива", 500, risk_pct=1) == "предпазлива"
    book = demo.load()
    assert book["active"] == "предпазлива" and book["accounts"]["демо 1"]["balance"] == 1000
    with pytest.raises(ValueError, match="Вече има"):
        demo.create("демо 1", 100)
    with pytest.raises(ValueError, match="поне 10"):
        demo.create("x", 5)
    with pytest.raises(ValueError, match="между"):
        demo.create("x", 100, risk_pct=20)


def test_delete_reset_and_choose_by_the_spoken_name():
    demo.create("", 1000)
    demo.create("Предпазлива", 500, risk_pct=1)
    assert demo.choose("демо 1") == "демо 1" and demo.load()["active"] == "демо 1"
    book = demo.load()
    book["accounts"]["демо 1"]["balance"] = 1234.0
    demo.save(book)
    assert demo.reset("демо 1") == ["демо 1"] and demo.load()["accounts"]["демо 1"]["balance"] == 1000
    assert demo.delete("предпазливата") == "Предпазлива"
    assert list(demo.load()["accounts"]) == ["демо 1"]
    with pytest.raises(ValueError, match="Няма демо сметка"):
        demo.delete("никаква")
    assert demo.reset("") == ["демо 1"]


def test_leva_and_euro_are_converted_to_dollars(monkeypatch):
    monkeypatch.setattr(demo, "_eur_per_usd", lambda: 0.9)
    assert demo.to_usd(1000, "долара") == 1000
    assert demo.to_usd(1955.83, "лева") == pytest.approx(1000 / 0.9)
    assert demo.to_usd(900, "евро") == pytest.approx(1000)
    with pytest.raises(ValueError):
        demo.to_usd(1, "йени")


def test_demo_accounts_hold_one_position_per_coin():
    account = demo.new_account(1000)
    opened = demo.open_signals(account, [sig(), sig(strategy="pullback")])
    assert len(opened) == 1 and opened[0]["size"] == pytest.approx(20.0)   # 2 % of 1000 $ over a 1 $ stop
    assert demo.open_signals(account, [sig(coin="ETH")])[0]["coin"] == "ETH"


def test_manual_trades_and_closing_at_market():
    account = demo.new_account(1000, risk_pct=1)
    trade = demo.open_manual(account, "SOL", "short", 100.0, 101.0, 98.0, "без сигнал")
    assert trade["size"] == pytest.approx(10.0)
    with pytest.raises(ValueError, match="вече има позиция"):
        demo.open_manual(account, "SOL", "long", 100.0, 99.0, 102.0, "без сигнал")
    closed = demo.close_manual(account, "SOL", 99.0)
    assert len(closed) == 1 and closed[0]["why"] == "ръчно" and account["open"] == []
    assert account["balance"] > 1000                        # a short from 100 to 99, after the costs
    assert demo.close_manual(account, "BTC", 1.0) == []


def test_step_trades_only_checked_strategies_unless_all_signals(monkeypatch):
    report = {"time": 0, "coins": {"BTC": {"breakout": GOOD}}}
    book = {"accounts": {"демо 1": demo.new_account(1000), "смел": demo.new_account(1000, all_signals=True)},
            "active": "демо 1"}
    p = SimpleNamespace(h1=candles([(100.0, 100.5, 99.5, 100.0)]), funding_t=[], funding_v=[])
    monkeypatch.setattr(signals, "latest", lambda p_: [sig(strategy="pullback"), sig()])
    lines = demo.step(book, {"BTC": p}, report)
    assert [t["strategy"] for t in book["accounts"]["демо 1"]["open"]] == ["breakout"]
    assert [t["strategy"] for t in book["accounts"]["смел"]["open"]] == ["pullback"]
    assert any(line.startswith("DEMO демо 1: отворих лонг на биткойн") for line in lines)


def test_step_settles_and_reports_the_result(monkeypatch):
    account = demo.new_account(1000)
    demo.open_signals(account, [sig()])
    book = {"accounts": {"демо 1": account}, "active": "демо 1"}
    p = SimpleNamespace(h1=candles([(100.0, 100.5, 99.5, 100.2), (100.2, 102.3, 100.0, 102.0)]), funding_t=[],
                        funding_v=[])
    monkeypatch.setattr(signals, "latest", lambda p_: [])
    lines = demo.step(book, {"BTC": p}, None)
    assert account["open"] == [] and account["balance"] > 1000
    assert lines[0].startswith("DEMO демо 1: затворих лонг на биткойн (цел): +")
    assert demo.by_strategy(account) == {"breakout": {"n": 1, "wins": 1, "r": pytest.approx(1.87, abs=0.01)}}


def test_equity_counts_open_positions():
    account = demo.new_account(1000)
    demo.open_signals(account, [sig()])                    # long 20 BTC from 100
    assert demo.equity(account, {"BTC": 101.0}) == pytest.approx(1020.0)
    assert demo.equity(account, {}) == 1000.0
