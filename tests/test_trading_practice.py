import copy

import pytest

from orion.trading import backtest, data, exchange, journal, lab, market, practice, settings, signals
from orion.trading.backtest import Stats
from orion.trading.data import HOUR, Bars
from orion.trading.risk import Limits
from orion.trading.signals import Signal
from test_trading_signals import random_walk


@pytest.fixture(autouse=True)
def temp_files(monkeypatch, tmp_path):
    monkeypatch.setattr(practice, "PRACTICE", tmp_path / "practice.json")
    monkeypatch.setattr(lab, "LAB", tmp_path / "lab.json")
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(signals, "PARAMS_FILE", tmp_path / "params.json")


def sig(time=10 * HOUR, strategy="pullback"):
    return Signal("BTC", strategy, "long", time, 100.0, 99.0, 102.0, 4, ["отскок в тренда"])


def candles(rows, start=10 * HOUR):
    bars = Bars(HOUR)
    for k, (o, h, l, c) in enumerate(rows):
        bars.add(start + k * HOUR, o, h, l, c, 1.0)
    return bars


def test_open_signals_sizes_like_a_real_trade_and_does_not_repeat():
    state = practice.load()
    assert practice.open_signals(state, [sig()], "current", Limits()) == 1
    assert state["open"][0]["size"] == pytest.approx(200.0)     # 2 % of 10 000 $ over a 1 $ stop
    assert practice.open_signals(state, [sig()], "current", Limits()) == 0
    assert practice.open_signals(state, [sig()], "candidate", Limits()) == 1


def test_settle_books_the_result_and_expires_what_is_too_old():
    state = practice.load()
    practice.open_signals(state, [sig()], "current", Limits())
    state["open"].append({**sig(time=1 * HOUR, strategy="breakout").to_dict(), "variant": "current", "size": 1.0})
    bars = candles([(100.0, 100.5, 99.5, 100.2), (100.2, 102.3, 100.0, 102.0)])
    closed = practice.settle(state, {"BTC": bars}, {})
    assert len(closed) == 1 and closed[0]["why"] == "цел"
    paid = 2 * data.DEFAULT_FUNDING
    r = (0.02 - 0.0013 - paid) / 0.01
    assert state["balance"] == pytest.approx(10_000 + r * 200.0)
    assert state["open"] == []
    assert [t["status"] for t in state["closed"]] == ["closed", "expired"]
    assert practice.by_strategy(state) == {"pullback": {"n": 1, "wins": 1, "r": pytest.approx(r, abs=1e-3)}}


def fake_prepared():
    h1 = random_walk(1200)
    return signals.prepare("BTC", h1, data.resample(h1, 4 * HOUR), data.resample(h1, 24 * HOUR), [],
                           copy.deepcopy(signals.DEFAULTS))


def test_a_round_opens_settles_and_checks_the_testnet_once_a_day(monkeypatch):
    p = fake_prepared()
    monkeypatch.setattr(market, "live", lambda coin, params=None: p)
    monkeypatch.setattr(signals, "latest", lambda p_: [Signal("BTC", "pullback", "long", p.h1.end(len(p.h1) - 1),
                                                              p.h1.c[-1], p.h1.c[-1] * 0.99, p.h1.c[-1] * 1.02, 4, [])])
    monkeypatch.setattr(lab, "step", lambda state, log=print: "")
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    checks = []
    monkeypatch.setattr(exchange, "testnet_check", lambda: (checks.append(1), "Проверката мина.")[1])
    first = practice.run()
    assert first.opened == 1 and first.testnet_note == "Проверката мина." and first.balance == 10_000.0
    second = practice.run()
    assert second.opened == 0 and second.testnet_note == "" and checks == [1]
    assert practice.load()["open"][0]["variant"] == "current"
    assert "тренировъчната сметка е 10 000 $ (+0.0 %)" in first.summary()


def test_lab_variants_and_the_margin():
    current = signals.DEFAULTS
    assert len(lab.variants("pullback", current["pullback"])) == 23
    assert len(lab.variants("breakout", current["breakout"])) == 23
    assert len(lab.variants("reversal", current["reversal"])) == 17
    assert lab.better(0.3, 0.2) and not lab.better(0.21, 0.2) and lab.better(0.05, -0.1)


def closed(strategy, variant, r, n, since=0):
    return [{"strategy": strategy, "variant": variant, "status": "closed", "r": r, "time": since + k}
            for k in range(n)]


def test_gate_b_promotes_only_after_20_better_practice_trades(monkeypatch):
    promoted = []
    monkeypatch.setattr(signals, "save_params", lambda strategy, numbers, why: promoted.append((strategy, numbers)))
    monkeypatch.setattr(lab, "search", lambda strategy, markets: None)
    lab.save({"candidates": {"breakout": {"params": {"channel": 48}, "since": 0}}, "log": [], "searched": {}})
    state = {"closed": closed("breakout", "candidate", 0.5, 19) + closed("breakout", "current", 0.1, 20)}
    assert lab.step(state, markets_by_coin={}) == ""
    assert promoted == [] and "breakout" in lab.candidates()
    state["closed"] += closed("breakout", "candidate", 0.5, 1, since=100)
    note = lab.step(state, markets_by_coin={})
    assert "минаха и двете проверки" in note and promoted == [("breakout", {"channel": 48})]
    assert lab.candidates() == {}


def test_gate_b_rejects_a_variant_that_does_worse(monkeypatch):
    monkeypatch.setattr(signals, "save_params", lambda *args: pytest.fail("must not promote"))
    monkeypatch.setattr(lab, "search", lambda strategy, markets: None)
    lab.save({"candidates": {"pullback": {"params": {"fast": 13}, "since": 0}}, "log": [], "searched": {}})
    state = {"closed": closed("pullback", "candidate", 0.1, 20) + closed("pullback", "current", 0.3, 20)}
    assert "не издържа тренировката" in lab.step(state, markets_by_coin={})
    assert lab.candidates() == {}


def test_gate_a_starts_a_trial_and_waits_a_week_before_searching_again(monkeypatch):
    good = Stats(40, 0.5, 0.35, 0.65, 0.4, 1.8, 4.0)
    old = Stats(40, 0.45, 0.3, 0.6, 0.2, 1.3, 5.0)
    searched = []
    monkeypatch.setattr(lab, "search", lambda strategy, markets: (searched.append(strategy), ({"fast": 13}, good, old))[1])
    note = lab.step({"closed": []}, markets_by_coin={})
    assert "пробвам нови числа за „отскок в тренда“" in note
    assert lab.candidates() == {"pullback": {"fast": 13}}
    lab.step({"closed": []}, markets_by_coin={})
    lab.step({"closed": []}, markets_by_coin={})
    lab.step({"closed": []}, markets_by_coin={})
    assert searched == ["pullback", "breakout", "reversal"]          # then nothing until a week has passed


def test_search_on_real_candles_returns_a_variant_and_both_judgements():
    p = fake_prepared()
    numbers, new, old = lab.search("pullback", {"BTC": p})
    assert numbers in lab.variants("pullback", signals.load_params()["pullback"])
    assert isinstance(new, Stats) and isinstance(old, Stats)
