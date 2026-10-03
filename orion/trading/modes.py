"""
The two trading buttons — DEMO TEST and REAL TRADE: the setting, the button in the window (trading.on_switch)
and what Orion says. The skills, the reflexes and the window all go through here.
"""
from .. import confirm, trading
from . import autopilot, demo, settings, texts


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


def set_real(on: bool, by_button: bool = False) -> str:
    """REAL TRADE: while it is on, the autopilot trades the real account by itself. The window button switches
    it at once (the click is sir's decision); by voice or chat a dialog asks first — the microphone hears the
    TV. Switching off never asks. Each switch from off to on starts the account stop's count again."""
    network = settings.network()
    where = "тестовата мрежа" if network == "testnet" else "ИСТИНСКИ пари"
    was_on = settings.enabled()
    if on and not was_on and not by_button:
        title = f"Автономна търговия · {'ТЕСТОВА МРЕЖА' if network == 'testnet' else 'РЕАЛНИ ПАРИ'}"
        if not confirm.ask(title, f"Орион търгува сам ({where})", texts.autopilot_terms(settings.limits()),
                           "Включи"):
            return "Добре, сър — REAL TRADE остава спрян."
    settings.set_enabled(on)
    trading.on_switch("real", bool(on))
    if not on:
        return ("Спрях истинската търговия — няма да отварям истински сделки. Отворените позиции остават със "
                "стоповете си.")
    if not was_on:
        autopilot.reset_peak()
    if not settings.account(network):
        return f"Включих REAL TRADE ({where}), но Hyperliquid не е свързан — кажете „свържи Hyperliquid“."
    return (f"Включих REAL TRADE ({where}). Търгувам сам по проверените стратегии — "
            f"{settings.limits().risk_pct:g} % риск на сделка, стоп и цел в борсата. Ще Ви казвам за всяка сделка.")
