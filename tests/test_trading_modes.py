import pytest

from orion import trading
from orion.trading import demo, modes, settings


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


def test_real_trade_says_what_is_missing(switched, monkeypatch):
    assert "не е свързан" in modes.set_real(True) and settings.enabled()
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    assert "„Одобри“" in modes.set_real(True)
    assert "Спрях истинската търговия" in modes.set_real(False) and not settings.enabled()
    assert ("real", False) in switched
