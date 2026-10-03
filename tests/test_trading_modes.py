import pytest

from orion import confirm, trading
from orion.trading import autopilot, demo, modes, settings


@pytest.fixture(autouse=True)
def switched(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "s.json")
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "demo.json")
    calls = []
    monkeypatch.setattr(trading, "on_switch", lambda name, on: calls.append((name, on)))
    return calls


def test_demo_test_on_creates_the_first_account(switched):
    text = modes.set_demo(True)
    assert "„демо 1“ с 1000 долара" in text and settings.demo_on()
    assert list(demo.load()["accounts"]) == ["демо 1"] and switched == [("demo", True)]
    assert "„демо 1“" in modes.set_demo(True)
    assert len(demo.load()["accounts"]) == 1
    assert "Спрях демо теста" in modes.set_demo(False) and not settings.demo_on()


def test_the_button_switches_real_trade_at_once(switched, monkeypatch):
    monkeypatch.setattr(confirm, "handler", lambda *args: pytest.fail("the button does not ask"))
    assert "не е свързан" in modes.set_real(True, by_button=True) and settings.enabled()
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    assert "Търгувам сам по проверените стратегии — 2 % риск" in modes.set_real(True, by_button=True)
    assert "Спрях истинската търговия" in modes.set_real(False) and not settings.enabled()
    assert switched == [("real", True), ("real", True), ("real", False)]


def test_real_trade_by_voice_asks_first(switched, monkeypatch):
    asked = []
    monkeypatch.setattr(confirm, "handler", lambda *args: (asked.append(args), False)[1])
    assert modes.set_real(True) == "Добре, сър — REAL TRADE остава спрян."
    assert not settings.enabled() and switched == []
    title, summary, body, accept = asked[0]
    assert title == "Автономна търговия · ТЕСТОВА МРЕЖА" and accept == "Включи"
    assert "сам, без да пита" in body and "40 %" in body
    monkeypatch.setattr(confirm, "handler", lambda *args: (asked.append(args), True)[1])
    assert "Включих REAL TRADE" in modes.set_real(True) and settings.enabled()
    assert len(asked) == 2
    modes.set_real(True)                                # already on: nothing to ask
    assert len(asked) == 2


def test_switching_off_never_asks(switched, monkeypatch):
    settings.set_enabled(True)
    monkeypatch.setattr(confirm, "handler", lambda *args: pytest.fail("off does not ask"))
    assert "Спрях" in modes.set_real(False) and not settings.enabled()


def test_switching_on_starts_the_account_stop_again(switched):
    state = autopilot.load()
    state["peak"] = 500.0
    autopilot.save(state)
    modes.set_real(True, by_button=True)
    assert autopilot.load()["peak"] is None
    state = autopilot.load()
    state["peak"] = 700.0
    autopilot.save(state)
    modes.set_real(True, by_button=True)                # already on: the count goes on
    assert autopilot.load()["peak"] == 700.0
