from types import SimpleNamespace

import pytest

from orion.trading import backtest, demo, simulate, texts
from orion.trading.backtest import Trade
from orion.trading.data import HOUR, Bars

DAY = 24 * HOUR
GOOD = {"trades": 40, "win_rate": 0.5, "win_low": 0.35, "win_high": 0.65, "avg_r": 0.3, "profit_factor": 1.6,
        "max_drawdown_r": 5.0}


def markets():
    clock = Bars(HOUR, t=list(range(0, 400 * DAY, HOUR)))     # 400 days — only the clock matters here
    return {coin: SimpleNamespace(h1=clock, coin=coin) for coin in ("BTC", "ETH", "SOL")}


def trade(coin, strategy, entry_day, exit_day, r):
    return Trade(coin, strategy, "long", entry_day * DAY, exit_day * DAY, 100.0, 100.0, 99.0, 102.0, r, "цел")


def replay(monkeypatch, trades, enabled, **kwargs):
    calls = []

    def fake(p, strategy, start, end):
        calls.append((p.coin, strategy, start, end))
        return [t for t in trades if t.coin == p.coin and t.strategy == strategy]

    monkeypatch.setattr(backtest, "simulate", fake)
    report = {"time": 0, "coins": {coin: {s: GOOD for s in names} for coin, names in enabled.items()}}
    return simulate.run(1000.0, report=report, markets=markets(), **kwargs), calls


def test_compounding_and_the_drawdown(monkeypatch):
    result, _ = replay(monkeypatch, [trade("BTC", "breakout", 100, 101, 2), trade("BTC", "breakout", 102, 103, -1)],
                       {"BTC": ["breakout"]})
    assert result.final == pytest.approx(1019.2)               # +40 on 1000, then −20.8 on 1040
    assert (result.trades, result.wins) == (2, 1)
    assert result.max_drawdown_pct == pytest.approx(2.0)
    assert list(result.months.values()) == [pytest.approx(1.92)]
    assert result.return_pct == pytest.approx(1.92)


def test_one_position_per_coin_but_coins_trade_together(monkeypatch):
    trades = [trade("BTC", "breakout", 100, 110, 1), trade("BTC", "pullback", 101, 102, 1),
              trade("ETH", "breakout", 101, 102, -1)]
    result, _ = replay(monkeypatch, trades, {"BTC": ["breakout", "pullback"], "ETH": ["breakout"]})
    assert (result.trades, result.wins, result.final) == (2, 1, pytest.approx(1000.0))
    assert result.max_drawdown_pct == pytest.approx(2.0)


def test_only_checked_strategies_unless_all_signals(monkeypatch):
    result, calls = replay(monkeypatch, [], {"BTC": ["breakout"]})
    assert [(c, s) for c, s, _, _ in calls] == [("BTC", "breakout")]
    assert result.strategies == {"BTC": ["breakout"], "ETH": [], "SOL": []}
    _, calls = replay(monkeypatch, [], {}, all_signals=True)
    assert len(calls) == 9


def test_the_window_starts_days_before_the_last_candle(monkeypatch):
    _, calls = replay(monkeypatch, [], {"BTC": ["breakout"]}, days=30)
    assert calls[0][2:] == ((400 - 30) * 24, 400 * 24)


def test_what_orion_says():
    result = simulate.Result(1000.0, 1019.2, 2, 1, 2.0, {"04.2026": 1.92, "05.2026": -0.5}, 365,
                             {"BTC": ["breakout"], "ETH": [], "SOL": []})
    text = texts.simulation(result, 2.0, False)
    assert "проверените стратегии (пробив на биткойн)" in text
    assert "накрая 1 019.20 $ (+1.9 %)" in text and "Най-голямо падане 2.0 %" in text
    assert "Най-добър месец 04.2026 (+1.9 %), най-лош 05.2026 (-0.5 %)" in text
    assert text.endswith("Миналото не гарантира бъдещето.")
    empty = simulate.Result(1000.0, 1000.0, 0, 0, 0.0, {}, 365, {"BTC": [], "ETH": [], "SOL": []})
    assert "Нито една стратегия не мина проверката" in texts.simulation(empty, 2.0, False)


def test_demo_sentences(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "demo.json")
    assert texts.demo_created("демо 1", 1111.111, 1.0, False, 1955.83, "лева") == (
        "Направих демо сметка „демо 1“ с 1 111.11 $ (1 956 лева) и 1 % риск — само проверените стратегии. "
        "Парите са измислени, цените — истински.")
    account = demo.new_account(1000)
    account["open"].append({"coin": "BTC", "side": "long", "entry": 100.0, "size": 2.0})
    book = {"accounts": {"демо 1": account}, "active": "демо 1"}
    status = texts.demo_status(book, {"BTC": 110.0}, True)
    assert status.splitlines()[1] == ("„демо 1“: 1 020.00 $ (+2.0 % от 1 000.00 $), 0 приключени сделки, 0 на "
                                      "печалба, отворени: биткойн лонг (избрана).")
    assert "DEMO TEST е изключен" in texts.demo_status(book, {}, False)
