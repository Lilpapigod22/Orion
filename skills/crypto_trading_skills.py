"""
Крипто прогнози и търговия: биткойн, етериум и солана на Hyperliquid — и демо сметки с измислени пари.
Числата идват от кода (три стратегии с честна проверка върху историята). На демо сметките Орион търгува сам
(DEMO TEST); всяка истинска сделка чака „Одобри“ от сър (REAL TRADE).
"""
from datetime import datetime

from orion import confirm, markets, orion_tool, trading
from orion.trading import (COINS, NAMES, backtest, coin_from_text, data, demo, exchange, journal, market, modes,
                           risk, settings, signals, simulate, texts)

# The forecast chart — app.py shows it in the journal after crypto_forecast.
last_chart: dict | None = None
REFUSALS = (risk.RiskError, exchange.TradingError, ValueError)
MAINNET_WORDS = ("mainnet", "истински", "истински пари", "реални", "реални пари", "истинска", "истинската мрежа",
                 "за истински пари")
NEITHER = ("Включете DEMO TEST за демо сделки (без истински пари) или REAL TRADE за истински — с Вашето „Одобри“ "
           "за всяка сделка.")
NO_DEMO = "Нямате демо сметка — кажете „направи демо сметка с 1000 долара“."
RATE_DOWN = "Не мога да взема курса в момента — кажете сумата в долари."
_DEMO_WORDS = ("демо", "демото", "demo", "в демото")


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


def _to_demo(account: str) -> bool | None:
    """True — the demo account, False — the real account, None — neither button is on."""
    if account.strip():
        return True
    if settings.enabled():
        return False
    if settings.demo_on():
        return True
    return None


def _demo_name(book: dict, account: str) -> str:
    words = account.strip().lower()
    name = demo.find(book, account) if words and words not in _DEMO_WORDS else None
    name = name or demo.active(book)
    if not name:
        raise ValueError(NO_DEMO)
    return name


def _mids() -> dict:
    return {coin: asset.mid for coin, asset in data.assets().items()}


def _real_view() -> bool:
    """Positions/account questions: the real account with REAL TRADE on, or when a key is connected and the
    demo is not in use."""
    to_demo = _to_demo("")
    if to_demo is False:
        return True
    return to_demo is None and bool(settings.account(settings.network())) and not demo.load()["accounts"]


# --- Forecasts ---------------------------------------------------------------------------------
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


# --- Accounts and trades -------------------------------------------------------------------------
@orion_tool
def trading_positions() -> str:
    """Отворените позиции сега: в истинската сметка (REAL TRADE) или в демо сметките (DEMO TEST)."""
    if not _real_view():
        return demo_status() if demo.load()["accounts"] else NEITHER
    network = settings.network()
    try:
        state, _ = exchange.account_state(network)
    except REFUSALS as e:
        return str(e)
    return texts.positions_text(state, network)


@orion_tool
def trading_account() -> str:
    """Сметката: истинската в Hyperliquid (пари, днешна загуба, риск) или демо сметките."""
    if not _real_view():
        return demo_status() if demo.load()["accounts"] else NEITHER
    network = settings.network()
    try:
        state, _ = exchange.account_state(network)
    except REFUSALS as e:
        return str(e)
    return texts.account_text(state, network, settings.limits())


def _open_demo(account: str, coin: str, side: str, p, stop_gap: float, target_gap: float, strategy: str) -> str:
    try:
        price = _mids().get(coin) or p.h1.c[-1]
    except OSError:
        price = p.h1.c[-1]
    with demo._lock:
        book = demo.load()
        try:
            name = _demo_name(book, account)
            trade = demo.open_manual(book["accounts"][name], coin, side, price, price - stop_gap, price + target_gap,
                                     strategy, settings.limits())
        except ValueError as e:
            return str(e)
        demo.save(book)
    return texts.demo_opened(name, trade)


@orion_tool
def open_trade(coin: str, side: str, account: str = "") -> str:
    """Отваря сделка — лонг или шорт — на биткойн, етериум или солана. С DEMO TEST (или „в демото“) — веднага в
    демо сметката, без истински пари; с REAL TRADE — в Hyperliquid, след прозорец „Одобри“.

    Args:
        coin: Монетата — "биткойн", "етериум" или "солана".
        side: "лонг" (за покачване) или "шорт" (за спадане).
        account: "демо" или името на демо сметката, ако сделката е в демото; празно — според бутоните.
    """
    try:
        c, direction = coin_from_text(coin), _side(side)
    except ValueError as e:
        return str(e)
    to_demo = _to_demo(account)
    if to_demo is None:
        return NEITHER
    try:
        p = market.live(c)
    except OSError:
        return texts.NO_DATA
    signal = next((s for s in signals.latest(p) if s.side == direction), None)
    if signal:  # the distances of the signal — re-anchored to the price of the account it goes to
        stop_gap, target_gap = signal.entry - signal.stop, signal.target - signal.entry
        note, strategy = f"Сигнал: {signals.LABELS[signal.strategy]}, сила {signal.strength} от 5.", signal.strategy
    else:
        atr = p.s["atr1"][-1] or p.h1.c[-1] * 0.01
        sign = 1 if direction == "long" else -1
        stop_gap, target_gap = sign * 1.5 * atr, sign * 3.0 * atr
        note, strategy = "ВНИМАНИЕ: в момента няма сигнал в тази посока — влизате без сигнал.", "без сигнал"
    if to_demo:
        return _open_demo(account, c, direction, p, stop_gap, target_gap, strategy)
    network = settings.network()
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
def close_trade(coin: str, account: str = "") -> str:
    """Затваря позиция (или всички): в демо сметката — веднага; в Hyperliquid — след „Одобри“ от сър.

    Args:
        coin: Монетата ("биткойн", "етериум", "солана") или "всички".
        account: "демо" или името на демо сметката, ако е в демото; празно — според бутоните.
    """
    to_demo = _to_demo(account)
    if to_demo is None:
        return NEITHER
    try:
        coins = list(COINS) if coin.strip().lower() in ("всички", "всичко", "all") else [coin_from_text(coin)]
    except ValueError as e:
        return str(e)
    if to_demo:
        try:
            mids = _mids()
        except OSError:
            return texts.NO_DATA
        with demo._lock:
            book = demo.load()
            try:
                name = _demo_name(book, account)
            except ValueError as e:
                return str(e)
            chosen = book["accounts"][name]
            closed = [t for c in coins if c in mids for t in demo.close_manual(chosen, c, mids[c])]
            if not closed:
                return (f"В демо сметката „{name}“ нямате отворена позиция"
                        + (f" в {NAMES[coins[0]]}." if len(coins) == 1 else "."))
            demo.save(book)
        return texts.demo_closed(name, closed, chosen)
    try:
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
    """Спира истинската търговия (бутона REAL TRADE): Орион не отваря истински сделки, докато сър не я пусне."""
    return modes.set_real(False)


@orion_tool
def resume_trading() -> str:
    """Пуска истинската търговия (бутона REAL TRADE) — всяка сделка пак чака „Одобри“."""
    return modes.set_real(True)


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


# --- Demo accounts, the simulation, the buttons ------------------------------------------------------
@orion_tool
def create_demo_account(balance: float, name: str = "", currency: str = "USD", risk_pct: float = 2.0,
                        all_signals: bool = False) -> str:
    """Прави демо сметка с измислени пари (напр. 1000 долара), на която Орион търгува сам по истинските цени,
    без истински пари. Може да има няколко, с имена и свой риск.

    Args:
        balance: Началните пари, напр. 1000.
        name: Име на сметката (празно — „демо 1“, „демо 2“…).
        currency: Валутата на сумата: USD (по подразбиране), лева или евро.
        risk_pct: Колко % от сметката рискува на сделка (по подразбиране 2).
        all_signals: True — търгува и стратегиите, които не са минали проверката.
    """
    try:
        usd = demo.to_usd(float(balance), currency)
        made = demo.create(name, usd, float(risk_pct), bool(all_signals))
    except ValueError as e:
        return str(e)
    except OSError:
        return RATE_DOWN
    text = texts.demo_created(made, usd, float(risk_pct), bool(all_signals), float(balance), currency)
    if not settings.demo_on():
        text += " Включете DEMO TEST (бутона долу или „включи демо теста“), за да започна да търгувам на нея."
    return text


@orion_tool
def demo_status() -> str:
    """Как вървят демо сметките: баланс, печалба или загуба в %, сделки и отворени позиции."""
    book = demo.load()
    if not book["accounts"]:
        return NO_DEMO
    try:
        mids = _mids()
    except OSError:
        mids = {}
    return texts.demo_status(book, mids, settings.demo_on())


@orion_tool
def delete_demo_account(name: str) -> str:
    """Изтрива демо сметка.

    Args:
        name: Името на сметката, напр. "демо 1".
    """
    try:
        return f"Изтрих демо сметката „{demo.delete(name)}“."
    except ValueError as e:
        return str(e)


@orion_tool
def reset_demo_account(name: str = "") -> str:
    """Започва демо сметка отначало — същите пари и риск, без сделките (празно — всички демо сметки).

    Args:
        name: Името на сметката (празно — всички).
    """
    try:
        names = demo.reset(name)
    except ValueError as e:
        return str(e)
    return "Започнах отначало: " + ", ".join(f"„{n}“" for n in names) + "."


@orion_tool
def choose_demo_account(name: str) -> str:
    """Избира демо сметката, в която отиват командите „отвори…“ и „затвори…“.

    Args:
        name: Името на сметката.
    """
    try:
        return f"Избрах демо сметката „{demo.choose(name)}“."
    except ValueError as e:
        return str(e)


@orion_tool
def simulate_history(balance: float, days: int = 365, currency: str = "USD", risk_pct: float = 2.0,
                     all_signals: bool = False) -> str:
    """Симулация: какво би станало с дадена сума, ако Орион беше търгувал по стратегиите си през последните дни —
    краен баланс, най-голямо падане, най-добър и най-лош месец.

    Args:
        balance: Началните пари, напр. 1000.
        days: За колко дни назад (365 — година).
        currency: USD (по подразбиране), лева или евро.
        risk_pct: Риск на сделка в % (по подразбиране 2).
        all_signals: True — и стратегиите, които не са минали проверката.
    """
    try:
        usd = demo.to_usd(float(balance), currency)
    except ValueError as e:
        return str(e)
    except OSError:
        return RATE_DOWN
    report = backtest.load()
    if report is None and not all_signals:
        backtest.refresh_async()
        return texts.NO_REPORT
    try:
        result = simulate.run(usd, int(days), float(risk_pct), bool(all_signals), report)
    except OSError:
        return texts.NO_DATA
    return texts.simulation(result, float(risk_pct), bool(all_signals))


@orion_tool
def set_demo_test(on: bool) -> str:
    """Включва или спира DEMO TEST — Орион търгува сам на демо сметките, без истински пари.

    Args:
        on: True — включи, False — спри.
    """
    return modes.set_demo(bool(on))


@orion_tool
def set_real_trading(on: bool) -> str:
    """Включва или спира REAL TRADE — истинската сметка в Hyperliquid (всяка сделка с „Одобри“).

    Args:
        on: True — включи, False — спри.
    """
    return modes.set_real(bool(on))
