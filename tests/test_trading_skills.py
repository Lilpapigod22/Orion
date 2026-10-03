import copy
import sys

import pytest

import config
from orion import confirm, trading
from orion.tools import registry
from orion.trading import data, exchange, risk, signals
from orion.trading.signals import Signal
from test_trading_signals import random_walk


@pytest.fixture
def cts(monkeypatch, tmp_path):
    if not registry.names():
        registry.load_skills(config.SKILLS_DIR)
    module = sys.modules["skills.crypto_trading_skills"]
    monkeypatch.setattr(module.journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(module.settings, "SETTINGS_FILE", tmp_path / "settings.json")
    module.settings.set_enabled(True)  # REAL TRADE on — these tests are about the real path
    monkeypatch.setattr(module.backtest, "load", lambda: None)
    monkeypatch.setattr(module.backtest, "refresh_async", lambda lock=None: True)
    h1 = random_walk(1200)
    prepared = signals.prepare("BTC", h1, data.resample(h1, 4 * data.HOUR), data.resample(h1, 24 * data.HOUR), [],
                               copy.deepcopy(signals.DEFAULTS))
    monkeypatch.setattr(module.market, "live", lambda coin, params=None: prepared)
    module.prepared = prepared
    return module


def long_signal(entry=84000.0, stop=83000.0, target=86000.0):
    return Signal("BTC", "pullback", "long", 1, entry, stop, target, 4, ["отскок в тренда", "обемът е над средния"])


def test_a_forecast_with_a_signal(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [long_signal()])
    text = cts.crypto_forecast("биткойна")
    assert "Сигнал ЛОНГ — отскок в тренда, сила 4 от 5" in text
    assert "Защо: обемът е над средния." in text
    assert cts.texts.NO_REPORT in text and text.endswith(cts.texts.NOT_ADVICE)
    assert cts.last_chart["entry"] == 84000.0 and cts.last_chart["stop"] == 83000.0
    assert cts.journal.record(days=1)["open"] == 1


def test_a_forecast_without_a_signal_gives_the_24h_range(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [])
    text = cts.crypto_forecast("BTC")
    assert "Няма ясен сигнал" in text and "До 24 часа цената вероятно ще е между" in text


def test_no_data_means_no_forecast(cts, monkeypatch):
    def down(coin, params=None):
        raise OSError("no route")
    monkeypatch.setattr(cts.market, "live", down)
    assert cts.crypto_forecast("биткойн") == cts.texts.NO_DATA


def test_other_coins(cts):
    assert "само биткойн, етериум и солана" in cts.crypto_forecast("доги")


def account(mid):
    return lambda network: (risk.AccountState(1000.0), {"BTC": {"mid": mid, "sz_decimals": 5, "max_leverage": 40}})


def test_open_trade_re_anchors_the_signal_to_the_trading_network_price(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [long_signal()])
    monkeypatch.setattr(cts.exchange, "account_state", account(60000.0))     # the testnet price is far away
    placed = []
    monkeypatch.setattr(cts.exchange, "place", lambda plan, note="": (placed.append((plan, note)), "Отворих лонг")[1])
    assert cts.open_trade("биткойн", "лонг") == "Отворих лонг"
    plan, note = placed[0]
    assert (plan.entry, plan.stop, plan.target, plan.network) == (60000.0, 59000.0, 62000.0, "testnet")
    assert "отскок в тренда" in note
    assert cts.journal.open_trade_time("BTC") is not None


def test_open_trade_without_a_signal_warns_and_uses_atr(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [])
    monkeypatch.setattr(cts.exchange, "account_state", account(100.0))
    placed = []
    monkeypatch.setattr(cts.exchange, "place", lambda plan, note="": (placed.append((plan, note)), "Добре")[1])
    cts.open_trade("BTC", "short")
    plan, note = placed[0]
    atr = cts.prepared.s["atr1"][-1]
    assert plan.side == "short" and "ВНИМАНИЕ" in note
    assert plan.stop == risk.round_price(100.0 + 1.5 * atr, 5)
    assert plan.target == risk.round_price(100.0 - 3.0 * atr, 5)


def test_open_trade_proposes_again_after_a_price_move_then_gives_up(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [])
    monkeypatch.setattr(cts.exchange, "account_state", account(100.0))
    calls = []

    def moved(plan, note=""):
        calls.append(plan)
        raise exchange.PriceMoved(101.0)

    monkeypatch.setattr(cts.exchange, "place", moved)
    assert "твърде бързо" in cts.open_trade("BTC", "long")
    assert len(calls) == 2


def test_refusals_and_the_switch(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [])
    monkeypatch.setattr(cts.exchange, "account_state",
                        lambda network: (risk.AccountState(1000.0, {"BTC": {}}),
                                         {"BTC": {"mid": 100.0, "sz_decimals": 5, "max_leverage": 40}}))
    assert "Вече имате позиция в Биткойн" in cts.open_trade("BTC", "long")
    assert "лонг" in cts.open_trade("BTC", "нагоре-надолу")
    cts.pause_trading()
    assert "DEMO TEST" in cts.open_trade("BTC", "long")       # REAL TRADE off, DEMO TEST off
    cts.resume_trading()


def test_close_all(cts, monkeypatch):
    closed = []
    monkeypatch.setattr(cts.exchange, "close", lambda coins, network, reason="": (closed.append(coins), "Затворих: x")[1])
    assert cts.close_trade("всички") == "Затворих: x"
    assert closed == [["BTC", "ETH", "SOL"]]
    cts.close_trade("етериума")
    assert closed[-1] == ["ETH"]


def test_connect_opens_the_key_dialog(cts, monkeypatch):
    shown = []
    monkeypatch.setattr(trading, "show_key_dialog", shown.append)
    assert "app.hyperliquid-testnet.xyz" in cts.connect_hyperliquid()
    assert "ИСТИНСКИ" in cts.connect_hyperliquid("истински пари")
    assert shown == ["testnet", "mainnet"]


def test_mainnet_needs_the_warning_dialog(cts, monkeypatch):
    monkeypatch.setattr(confirm, "handler", lambda *args: False)
    assert "тестовата мрежа" in cts.switch_trading_network("истински пари")
    assert cts.settings.network() == "testnet"
    monkeypatch.setattr(confirm, "handler", lambda *args: True)
    assert cts.switch_trading_network("mainnet").startswith("Минах на истински пари")
    assert cts.settings.network() == "mainnet"
    cts.switch_trading_network("тестовата мрежа")
    assert cts.settings.network() == "testnet"


def test_texts_for_the_record_and_the_table(cts):
    texts = cts.texts
    assert "още няма приключили сигнали" in texts.record_text(
        {"days": 7, "n": 0, "wins": 0, "win_rate": 0, "avg_r": 0, "open": 2, "by_strategy": {}})
    summary = {"days": 7, "n": 4, "wins": 3, "win_rate": 0.75, "avg_r": 0.8, "open": 0,
               "by_strategy": {"breakout": {"n": 4, "wins": 3, "r": 3.2}}}
    assert texts.record_text(summary) == ("За последните 7 дни: 4 приключили сигнала, 3 на печалба (75 %), средно "
                                          "+0.80 пъти риска. По стратегии: пробив 3 от 4.")
    weak = {"trades": 40, "win_rate": 0.3, "win_low": 0.2, "win_high": 0.45, "avg_r": -0.1, "profit_factor": 0.8,
            "max_drawdown_r": 9.0}
    report = {"time": 0, "coins": {"BTC": {"pullback": weak, "breakout": weak, "reversal": weak,
                                           "range": {"hits": 70, "total": 100}, "from": 0, "to": 0}}}
    table = texts.strategy_table(report)
    assert "не мина" in table and "нямам предимство" in table
