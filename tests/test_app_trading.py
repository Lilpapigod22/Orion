import queue
import threading

import app
from orion.trading import exchange, settings


def bare_app(said, hud_calls):
    orion = app.Orion.__new__(app.Orion)
    orion.hud = lambda fn, *args: hud_calls.append((fn, args))
    orion._pending_lock, orion._pending, orion.tasks = threading.Lock(), 0, queue.Queue()
    orion.say = said.append
    return orion


def test_a_key_typed_in_the_chat_is_never_processed(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "s.json")
    said, hud_calls = [], []
    orion = bare_app(said, hud_calls)
    orion.ask("0x" + "ab" * 32)
    orion.ask(" ".join(["abandon"] * 11 + ["about"]))
    assert orion.tasks.empty()
    assert hud_calls[0] == ("showKeyDialog", ({"network": "testnet"},))
    assert "таен ключ" in said[0] and "ab" * 32 not in said[0]
    orion.ask("Колко е часът?")
    assert orion.tasks.get_nowait() == ("ask", "Колко е часът?", "text")


def test_save_trading_key_reports_the_result(monkeypatch):
    said = []
    orion = bare_app(said, [])
    api = app.HudApi(orion)
    result = api.save_trading_key("testnet", "0x123", "k" * 64)
    assert result["ok"] is False and "Адресът" in result["message"]
    monkeypatch.setattr(settings, "save_account", lambda network, address, key: "Запазих API ключа.")
    monkeypatch.setattr(exchange, "check_connection", lambda network: "Свързах се.")
    result = api.save_trading_key("testnet", "0x" + "a" * 40, "b" * 64)
    assert result == {"ok": True, "message": "Запазих API ключа. Свързах се."}
    assert said == ["Запазих API ключа. Свързах се."]
