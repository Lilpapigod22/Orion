"""
The two trading buttons — DEMO TEST and REAL TRADE: the setting, the button in the window (trading.on_switch)
and what Orion says. The skills, the reflexes and the window all go through here.
"""
from .. import trading
from . import demo, settings


def set_demo(on: bool) -> str:
    settings.set_demo(on)
    trading.on_switch("demo", bool(on))
    if not on:
        return ("Спрях демо теста. Демо сметките чакат — отворените им сделки ще се приключат по свещите, когато "
                "го включите пак.")
    book = demo.load()
    if not book["accounts"]:
        demo.create("демо 1", 1000.0)
        return ("Включих демо теста и направих демо сметка „демо 1“ с 1000 долара и 2 % риск. Търгувам сам по "
                "проверените стратегии, на истински цени, без истински пари.")
    names = ", ".join(f"„{name}“" for name in book["accounts"])
    return f"Включих демо теста — търгувам сам на демо сметките {names}, без истински пари."


def set_real(on: bool) -> str:
    settings.set_enabled(on)
    trading.on_switch("real", bool(on))
    if not on:
        return ("Спрях истинската търговия — няма да отварям истински сделки. Отворените позиции остават със "
                "стоповете си.")
    network = settings.network()
    where = "тестовата мрежа" if network == "testnet" else "ИСТИНСКИ пари"
    if not settings.account(network):
        return f"Включих REAL TRADE ({where}), но Hyperliquid не е свързан — кажете „свържи Hyperliquid“."
    return f"Включих REAL TRADE ({where}). Давам прогнози, когато питате, и всяка сделка чака Вашето „Одобри“."
