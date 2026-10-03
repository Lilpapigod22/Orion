import sys

import pytest

from orion.trading import settings

ADDRESS = "0x" + "a1" * 20
KEY = "b2" * 32


@pytest.fixture(autouse=True)
def temp_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "trading_settings.json")


def test_defaults_are_the_testnet_and_the_aggressive_limits():
    assert settings.network() == "testnet" and not settings.enabled() and not settings.demo_on()
    limits = settings.limits()
    assert (limits.risk_pct, limits.max_leverage, limits.daily_loss_pct, limits.max_positions) == (2.0, 10, 6.0, 3)
    assert limits.max_drawdown_pct == 40.0
    assert settings.account("testnet") is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_round_trip_hides_the_text():
    token = settings.protect("0x" + KEY)
    assert KEY not in token
    assert settings.unprotect(token) == "0x" + KEY


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_a_saved_key_is_encrypted_on_disk(tmp_path):
    message = settings.save_account("testnet", ADDRESS, KEY)
    assert "тестовата" in message
    assert KEY not in settings.SETTINGS_FILE.read_text(encoding="utf-8")
    assert settings.account("testnet") == (ADDRESS, "0x" + KEY)
    assert settings.account("mainnet") is None


@pytest.mark.parametrize("address, key, words", [
    (ADDRESS, " ".join(["abandon"] * 12), "думите за възстановяване"),
    ("0x123", KEY, "Адресът"),
    (ADDRESS, "123", "64 знака"),
])
def test_bad_input_is_refused(address, key, words):
    with pytest.raises(ValueError, match=words):
        settings.save_account("testnet", address, key)


def test_the_demo_test_switch_is_saved():
    settings.set_demo(True)
    assert settings.demo_on()
    settings.set_demo(False)
    assert not settings.demo_on()


def test_network_and_switch_are_saved():
    settings.set_network("mainnet")
    assert settings.network() == "mainnet"
    settings.set_enabled(False)
    assert not settings.enabled()
    settings.set_network("anything else")
    assert settings.network() == "testnet"


def test_a_settings_file_from_before_gets_the_account_stop():
    settings.SETTINGS_FILE.write_text('{"limits": {"risk_pct": 1.0}}', encoding="utf-8")
    limits = settings.limits()
    assert (limits.risk_pct, limits.max_drawdown_pct) == (1.0, 40.0)
