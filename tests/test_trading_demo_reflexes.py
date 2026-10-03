import json

import pytest

from orion import brain, reflexes, router


@pytest.mark.parametrize("text, tool, args", [
    ("искам да тренираш сметка която е с 1000 долара и да направиш 10 000 лв чисто симулационно",
     "create_demo_account", {"balance": 1000.0, "currency": "долара"}),
    ("Направи демо сметка „предпазлива“ с 500 долара и 1 % риск", "create_demo_account",
     {"balance": 500.0, "currency": "долара", "name": "предпазлива", "risk_pct": 1.0}),
    ("Направи демо сметка с 10 000 лева с всички сигнали", "create_demo_account",
     {"balance": 10000.0, "currency": "лева", "all_signals": True}),
    ("Симулирай 1000 долара за последната година", "simulate_history",
     {"balance": 1000.0, "currency": "долара", "days": 365}),
    ("Симулирай 500 долара за 6 месеца с 1% риск", "simulate_history",
     {"balance": 500.0, "currency": "долара", "days": 180, "risk_pct": 1.0}),
    ("Как върви демото?", "demo_status", {}),
    ("Покажи демо сметките", "demo_status", {}),
    ("Изтрий демо сметката „предпазлива“", "delete_demo_account", {"name": "предпазлива"}),
    ("Започни демото отначало", "reset_demo_account", {"name": ""}),
    ("Избери демо сметката „смел“", "choose_demo_account", {"name": "смел"}),
    ("Включи демо теста", "set_demo_test", {"on": True}),
    ("Спри демо теста", "set_demo_test", {"on": False}),
    ("Включи реал трейд", "set_real_trading", {"on": True}),
    ("Спри реал трейд", "set_real_trading", {"on": False}),
    ("Отвори лонг на биткойн в демото", "open_trade", {"coin": "биткойн в демото", "side": "long", "account": "демо"}),
    ("Затвори етериума в демото", "close_trade", {"coin": "етериума в демото", "account": "демо"}),
])
def test_demo_phrases_are_reflexes(text, tool, args):
    reflex = reflexes.respond(text)
    assert reflex is not None and reflex.tool == tool and reflex.arguments == args


@pytest.mark.parametrize("text", ["Как е демократичната партия?", "Покажи ми демонстрацията",
                                  "Разкажи ми за демократите"])
def test_words_that_only_contain_demo_are_not_about_the_demo(text):
    reflex = reflexes.respond(text)
    assert reflex is None or reflex.tool != "demo_status"
    default = brain.Brain._default_call(text)
    assert default is None or default[0] != "demo_status"


def test_plain_trading_phrases_are_unchanged():
    assert reflexes.respond("Отвори лонг на биткойн").arguments == {"coin": "биткойн", "side": "long"}


def test_the_router_and_the_nudge_know_the_demo():
    assert "skills.crypto_trading_skills" not in router.excluded_modules("Искам симулационна сметка")
    name, arguments = brain.Brain._default_call("Можеш ли да тренираш на демо сметка?")
    assert name == "demo_status" and json.loads(arguments) == {}
    assert {"demo_status", "simulate_history"} <= brain.READ_ONLY_TOOLS
