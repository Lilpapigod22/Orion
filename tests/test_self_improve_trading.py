import pytest

from orion.self_improve import TRADING_BAN, validate_skill_code

SKILL = """from orion import orion_tool
{imports}


@orion_tool
def my_skill(text: str) -> str:
    \"\"\"Прави нещо.\"\"\"
{body}
    return text
"""


def problems(imports="", body=""):
    return validate_skill_code(SKILL.format(imports=imports, body=body), set())[0]


@pytest.mark.parametrize("imports, body", [
    ("from orion.trading import exchange", "    exchange.auto_place(None)"),
    ("from orion.trading.autopilot import step", "    step({}, None, 'mainnet')"),
    ("import orion.trading.modes", "    orion.trading.modes.set_real(True)"),
    ("from orion import trading", "    trading.on_switch('real', True)"),
    ("import orion", "    orion.trading.settings.set_enabled(True)"),
    ("", "    from orion.trading import settings\n    settings.set_enabled(True)"),
    ("from skills.crypto_trading_skills import modes", "    modes.set_real(True, by_button=True)"),
    ("from skills import crypto_trading_skills as c", "    c.exchange.auto_close(['BTC'], 'mainnet')"),
    ("import skills.crypto_trading_skills", "    skills.crypto_trading_skills.settings.set_enabled(True)"),
])
def test_code_orion_writes_may_not_reach_trading(imports, body):
    assert TRADING_BAN in problems(imports, body)


def test_other_orion_modules_are_still_fine():
    assert problems("from orion import markets", "    markets.analyze") == []
    assert TRADING_BAN not in problems("import json", "    json.dumps({'trading': 1})")
    assert TRADING_BAN not in problems("from skills import util_skills", "    util_skills")
