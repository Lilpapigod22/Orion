import copy
import sys

import pytest

import config
from orion import trading
from orion.tools import registry
from orion.trading import data, signals, simulate
from test_trading_signals import random_walk


@pytest.fixture
def cts(monkeypatch, tmp_path):
    if not registry.names():
        registry.load_skills(config.SKILLS_DIR)
    module = sys.modules["skills.crypto_trading_skills"]
    monkeypatch.setattr(module.journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(module.settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(module.demo, "DEMO_FILE", tmp_path / "demo.json")
    monkeypatch.setattr(module.demo, "_eur_per_usd", lambda: 0.9)
    monkeypatch.setattr(module.backtest, "load", lambda: None)
    monkeypatch.setattr(module.backtest, "refresh_async", lambda lock=None: True)
    h1 = random_walk(1200)
    prepared = signals.prepare("BTC", h1, data.resample(h1, 4 * data.HOUR), data.resample(h1, 24 * data.HOUR), [],
                               copy.deepcopy(signals.DEFAULTS))
    monkeypatch.setattr(module.market, "live", lambda coin, params=None: prepared)
    monkeypatch.setattr(module.data, "assets",
                        lambda: {c: data.Asset(c, 100.0, 100.0, 0.0, 0.0, 0.0, 2, 20) for c in ("BTC", "ETH", "SOL")})
    monkeypatch.setattr(module.signals, "latest", lambda p: [])
    return module


def test_creating_demo_accounts(cts):
    text = cts.create_demo_account(1000)
    assert text.startswith("Направих демо сметка „демо 1“ с 1 000.00 $") and "DEMO TEST" in text
    text = cts.create_demo_account(1955.83, name="предпазлива", currency="лева", risk_pct=1)
    assert "„предпазлива“ с 1 111.11 $ (1 956 лева) и 1 % риск" in text
    assert "Вече има" in cts.create_demo_account(10, name="предпазлива")


def test_trades_go_to_the_demo_when_only_demo_test_is_on(cts):
    cts.settings.set_demo(True)
    cts.create_demo_account(1000)
    assert cts.open_trade("биткойн", "лонг").startswith("DEMO „демо 1“: отворих лонг на биткойн на 100.00")
    status = cts.demo_status()
    assert "„демо 1“" in status and "отворени: биткойн лонг" in status
    assert cts.close_trade("биткойна").startswith("DEMO „демо 1“: затворих биткойн (")
    assert cts.demo.load()["accounts"]["демо 1"]["open"] == []


def test_both_buttons_off_says_which_to_switch_on(cts):
    answer = cts.open_trade("BTC", "long")
    assert "DEMO TEST" in answer and "REAL TRADE" in answer


def test_saying_in_the_demo_overrides_real_trade(cts, monkeypatch):
    cts.settings.set_enabled(True)
    cts.create_demo_account(1000)
    monkeypatch.setattr(cts.exchange, "place", lambda *args, **kwargs: pytest.fail("no real order"))
    assert cts.open_trade("BTC", "long", account="демо").startswith("DEMO „демо 1“")


def test_no_demo_account_yet(cts):
    cts.settings.set_demo(True)
    assert "направи демо сметка" in cts.open_trade("BTC", "long")


def test_delete_reset_choose(cts):
    cts.create_demo_account(1000)
    cts.create_demo_account(500, name="смел")
    assert cts.choose_demo_account("демо 1") == "Избрах демо сметката „демо 1“."
    assert cts.reset_demo_account("смел") == "Започнах отначало: „смел“."
    assert cts.delete_demo_account("смел") == "Изтрих демо сметката „смел“."
    assert "Няма демо сметка" in cts.delete_demo_account("смел")


def test_buttons_by_voice(cts, monkeypatch):
    switched = []
    monkeypatch.setattr(trading, "on_switch", lambda name, on: switched.append((name, on)))
    assert "Включих демо теста" in cts.set_demo_test(True)
    assert "Спрях истинската търговия" in cts.pause_trading()
    assert "Включих REAL TRADE" in cts.set_real_trading(True)
    assert switched == [("demo", True), ("real", False), ("real", True)]


def test_the_simulation(cts, monkeypatch):
    monkeypatch.setattr(cts.backtest, "load", lambda: {"time": 0, "coins": {}})
    monkeypatch.setattr(cts.simulate, "run", lambda *args, **kwargs: simulate.Result(
        1000.0, 1100.0, 10, 6, 5.0, {"03.2026": 4.0}, 365, {"BTC": ["breakout"]}))
    text = cts.simulate_history(1000)
    assert "накрая 1 100.00 $ (+10.0 %)" in text and text.endswith("Миналото не гарантира бъдещето.")
    monkeypatch.setattr(cts.backtest, "load", lambda: None)
    assert cts.simulate_history(1000) == cts.texts.NO_REPORT


def test_without_a_key_orion_points_to_the_demo(cts):
    cts.settings.set_enabled(True)
    answer = cts.trading_positions()
    assert "свържи Hyperliquid" in answer and "направи демо сметка" in answer


def test_positions_and_account_show_the_demo_without_real_trade(cts):
    assert cts.trading_positions() == cts.NEITHER
    cts.create_demo_account(1000)
    assert cts.trading_positions().startswith("Демо сметките")
    assert cts.trading_account().startswith("Демо сметките")
