import json

import pytest

from orion import brain, reflexes, router
from orion.trading import exchange


@pytest.mark.parametrize("text, tool, args", [
    ("Орион, отвори лонг на биткойн", "open_trade", {"coin": "биткойн", "side": "long"}),
    ("Отвори шорт на етериума", "open_trade", {"coin": "етериума", "side": "short"}),
    ("влез лонк в солана", "open_trade", {"coin": "солана", "side": "long"}),
    ("шорт на BTC", "open_trade", {"coin": "BTC", "side": "short"}),
    ("Затвори позицията на биткойна", "close_trade", {"coin": "биткойна"}),
    ("затвори етериума", "close_trade", {"coin": "етериума"}),
    ("Затвори всички позиции", "close_trade", {"coin": "всички"}),
    ("Спри търговията", "pause_trading", {}),
    ("Пусни търговията", "resume_trading", {}),
    ("Какви позиции имам?", "trading_positions", {}),
    ("Свържи Hyperliquid", "connect_hyperliquid", {"network": "testnet"}),
    ("свържи хайперликуид за истински пари", "connect_hyperliquid", {"network": "mainnet"}),
    ("Мини на истински пари", "switch_trading_network", {"network": "mainnet"}),
    ("Мини на тестовата мрежа", "switch_trading_network", {"network": "testnet"}),
])
def test_trading_commands_are_reflexes(text, tool, args):
    reflex = reflexes.respond(text)
    assert reflex is not None and reflex.tool == tool and reflex.arguments == args


@pytest.mark.parametrize("text", ["отвори Chrome", "затвори Steam", "какво мислиш за лонг на биткойн", "затвори доги"])
def test_other_phrases_are_not_trading(text):
    assert reflexes._trading_command(reflexes._plain(text)) is None


def test_close_everything_only_with_known_positions(monkeypatch):
    monkeypatch.setattr(exchange, "last_open", set())
    assert reflexes._trading_command("затвори всичко") is None
    monkeypatch.setattr(exchange, "last_open", {"BTC"})
    assert reflexes._trading_command("затвори всичко").arguments == {"coin": "всички"}


def test_the_trading_group_is_shown_only_when_relevant():
    assert "skills.crypto_trading_skills" not in router.excluded_modules("Какво ще прави солана?")
    assert "skills.crypto_trading_skills" not in router.excluded_modules("Колко пъти позна тази седмица?")
    assert "skills.crypto_trading_skills" in router.excluded_modules("Пусни радио Хоризонт")


def test_a_forecast_question_nudges_towards_crypto_forecast():
    name, arguments = brain.Brain._default_call("Какво ще прави биткойнът днес?")
    assert name == "crypto_forecast" and json.loads(arguments) == {"coin": "Какво ще прави биткойнът днес?"}
    assert brain.Brain._default_call("Направи ми анализ на златото")[0] != "crypto_forecast"
    assert {"crypto_forecast", "trading_positions"} <= brain.READ_ONLY_TOOLS
