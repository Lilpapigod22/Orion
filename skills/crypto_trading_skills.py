"""
Крипто прогнози и търговия: биткойн, етериум и солана на Hyperliquid. Числата идват от кода — три
стратегии с честна проверка върху историята; всяка истинска сделка чака „Одобри“ от сър.
"""
from datetime import datetime

from orion import confirm, markets, orion_tool, trading
from orion.trading import (COINS, NAMES, backtest, coin_from_text, exchange, journal, market, risk, settings,
                           signals, texts)

# The forecast chart — app.py shows it in the journal after crypto_forecast.
last_chart: dict | None = None
REFUSALS = (risk.RiskError, exchange.TradingError, ValueError)
MAINNET_WORDS = ("mainnet", "истински", "истински пари", "реални", "реални пари", "истинска", "истинската мрежа",
                 "за истински пари")


def _side(text: str) -> str:
    word = text.strip().lower()
    if word in ("long", "лонг", "лонк", "купи", "покупка", "нагоре"):
        return "long"
    if word in ("short", "шорт", "шорд", "продай", "продажба", "надолу"):
        return "short"
    raise ValueError("Кажете „лонг“ (за покачване) или „шорт“ (за спадане).")


def _network_of(text: str) -> str:
    return "mainnet" if text.strip().lower() in MAINNET_WORDS else "testnet"


def _chart(p: signals.Prepared, signal) -> dict:
    series = markets.Series(p.coin, NAMES[p.coin], "USD", "1h", [datetime.fromtimestamp(t / 1000) for t in p.h1.t],
                            list(p.h1.o), list(p.h1.h), list(p.h1.l), list(p.h1.c), kind="CRYPTOCURRENCY")
    chart = markets.chart_data(series, markets.analyze(series))
    if signal:
        chart.update(entry=signal.entry, stop=signal.stop, target=signal.target)
    return chart


@orion_tool
def crypto_forecast(coin: str) -> str:
    """Прогноза за биткойн, етериум или солана за следващите часове до 2 дни: посока (лонг, шорт или
    „няма сигнал“), вход, стоп, цел, сила и колко често такъв сигнал е печелил в честната проверка.

    Args:
        coin: Монетата — "биткойн", "етериум" или "солана".
    """
    global last_chart
    try:
        c = coin_from_text(coin)
    except ValueError as e:
        return f"Сър, {e}."
    try:
        p = market.live(c)
    except OSError:
        return texts.NO_DATA
    found = signals.latest(p)
    for s in found:
        journal.add_signal(s, "asked")
    report = backtest.load()
    if report is None:
        backtest.refresh_async()
    last_chart = _chart(p, texts.best(found, report) if found else None)
    return texts.forecast(c, found, signals.context(p), report)


@orion_tool
def crypto_signals() -> str:
    """Сигналите сега за биткойн, етериум и солана наведнъж: кой има лонг или шорт сигнал и колко е силен."""
    report = backtest.load()
    lines = []
    for c in COINS:
        try:
            p = market.live(c)
        except OSError:
            return texts.NO_DATA
        found = signals.latest(p)
        for s in found:
            journal.add_signal(s, "asked")
        lines.append(texts.signal_line(c, found, report))
    return "\n".join(lines + [texts.NOT_ADVICE])


@orion_tool
def strategy_report() -> str:
    """Колко добри са стратегиите на Орион: проверката върху историята за всяка монета (сделки, колко често
    печелят, средна печалба след таксите) и кои са минали проверката."""
    report = backtest.load()
    if report is None:
        backtest.refresh_async()
        return texts.NO_REPORT
    return texts.strategy_table(report)


@orion_tool
def forecast_record(days: int = 7) -> str:
    """Колко пъти са познали прогнозите на Орион през последните дни — истинските резултати на сигналите.

    Args:
        days: За колко дни назад, напр. 7 за седмица или 30 за месец.
    """
    return texts.record_text(journal.record(max(1, int(days))))


@orion_tool
def trading_positions() -> str:
    """Отворените позиции в Hyperliquid сега: монета, лонг или шорт, размер и печалба или загуба."""
    network = settings.network()
    try:
        state, _ = exchange.account_state(network)
    except REFUSALS as e:
        return str(e)
    return texts.positions_text(state, network)


@orion_tool
def trading_account() -> str:
    """Сметката в Hyperliquid: колко пари има, днешната загуба спрямо лимита и рискът на сделка."""
    network = settings.network()
    try:
        state, _ = exchange.account_state(network)
    except REFUSALS as e:
        return str(e)
    return texts.account_text(state, network, settings.limits())


@orion_tool
def open_trade(coin: str, side: str) -> str:
    """Отваря истинска сделка — лонг или шорт — на биткойн, етериум или солана в Hyperliquid. Орион
    изчислява размера по лимитите и показва прозорец „Одобри“; без него нищо не се отваря.

    Args:
        coin: Монетата — "биткойн", "етериум" или "солана".
        side: "лонг" (за покачване) или "шорт" (за спадане).
    """
    try:
        c, direction = coin_from_text(coin), _side(side)
    except ValueError as e:
        return str(e)
    if not settings.enabled():
        return "Търговията е спряна. Кажете „пусни търговията“, за да я включите."
    network = settings.network()
    try:
        p = market.live(c)
    except OSError:
        return texts.NO_DATA
    signal = next((s for s in signals.latest(p) if s.side == direction), None)
    if signal:  # the distances of the signal — re-anchored to the price of the network sir trades on
        stop_gap, target_gap = signal.entry - signal.stop, signal.target - signal.entry
        note, strategy = f"Сигнал: {signals.LABELS[signal.strategy]}, сила {signal.strength} от 5.", signal.strategy
    else:
        atr = p.s["atr1"][-1] or p.h1.c[-1] * 0.01
        sign = 1 if direction == "long" else -1
        stop_gap, target_gap = sign * 1.5 * atr, sign * 3.0 * atr
        note, strategy = "ВНИМАНИЕ: в момента няма сигнал в тази посока — влизате без сигнал.", "без сигнал"
    for _ in range(2):
        try:
            state, coins = exchange.account_state(network)
            details = coins[c]
            entry = details["mid"]
            plan = risk.plan(c, direction, entry, entry - stop_gap, entry + target_gap, state, details["sz_decimals"],
                             details["max_leverage"], settings.limits(), network)
            extra = (f"\nРазмерът е намален заради лимита — рискът е {plan.risk_usd:.2f} $."
                     if plan.reduced else "")
            answer = exchange.place(plan, note + extra)
        except exchange.PriceMoved:
            continue  # the price moved while sir was deciding: new numbers, a new dialog
        except REFUSALS as e:
            return str(e)
        if answer.startswith("Отворих"):
            journal.add_trade(plan, strategy)
        return answer
    return "Цената се движи твърде бързо — сделката не е отворена. Опитайте пак след малко."


@orion_tool
def close_trade(coin: str) -> str:
    """Затваря отворена позиция в Hyperliquid (или всички) — след „Одобри“ от сър.

    Args:
        coin: Монетата ("биткойн", "етериум", "солана") или "всички".
    """
    try:
        coins = list(COINS) if coin.strip().lower() in ("всички", "всичко", "all") else [coin_from_text(coin)]
        answer = exchange.close(coins, settings.network())
    except REFUSALS as e:
        return str(e)
    if answer.startswith("Затворих"):
        for c in coins:
            journal.close_trade(c)
    return answer


@orion_tool
def move_stop_to_entry(coin: str) -> str:
    """Мести стопа на входната цена (без загуба), когато сделката е на печалба — след „Одобри“ от сър.

    Args:
        coin: Монетата — "биткойн", "етериум" или "солана".
    """
    try:
        return exchange.move_stop_to_entry(coin_from_text(coin), settings.network())
    except REFUSALS as e:
        return str(e)


@orion_tool
def connect_hyperliquid(network: str = "testnet") -> str:
    """Свързва Орион с Hyperliquid (където Trust Wallet търгува Perps): отваря прозореца за API ключа.

    Args:
        network: "testnet" (тестова мрежа, по подразбиране) или "mainnet" (истински пари).
    """
    net = _network_of(network)
    trading.show_key_dialog(net)
    return texts.CONNECT_STEPS[net]


@orion_tool
def pause_trading() -> str:
    """Спира търговията: Орион не отваря нови сделки, докато сър не каже „пусни търговията“."""
    settings.set_enabled(False)
    return "Спрях търговията — няма да отварям нови сделки. Отворените позиции остават със стоповете си."


@orion_tool
def resume_trading() -> str:
    """Пуска търговията отново (всяка сделка пак чака „Одобри“)."""
    settings.set_enabled(True)
    return "Пуснах търговията отново — всяка сделка пак чака Вашето „Одобри“."


@orion_tool
def switch_trading_network(network: str) -> str:
    """Сменя мрежата за търговия: тестова мрежа или истински пари (с прозорец с предупреждение).

    Args:
        network: "testnet" или "mainnet" (истински пари).
    """
    if _network_of(network) == "mainnet":
        if not confirm.ask("Истински пари", "Минаване на РЕАЛНИ ПАРИ в Hyperliquid", texts.MAINNET_WARNING,
                           "Мини на истински пари"):
            return "Добре, сър — оставаме в тестовата мрежа."
        settings.set_network("mainnet")
        extra = "" if settings.account("mainnet") else \
            " Свържете ключа за истинската мрежа: кажете „свържи Hyperliquid за истински пари“."
        return "Минах на истински пари. Всяка сделка пак чака Вашето „Одобри“." + extra
    settings.set_network("testnet")
    return "Минах на тестовата мрежа — сделките са с тестови пари."
