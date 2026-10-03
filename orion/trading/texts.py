"""
Everything Orion says about forecasts, strategies, the record, the account and fills — in Bulgarian, built
only from numbers the code computed (the language model just reads it out).
"""
from datetime import datetime

from ..markets import _fmt
from . import NAMES, backtest, demo
from .signals import LABELS

SIDE = {"long": "ЛОНГ", "short": "ШОРТ"}
TREND = {1: "нагоре", -1: "надолу", 0: "без ясна посока"}
NOT_ADVICE = "Това е вероятност, не гаранция, и не е инвестиционен съвет."
NO_DATA = ("Няма връзка с пазарните данни на Hyperliquid в момента, затова не давам прогноза — не искам да Ви "
           "казвам стари числа. Опитайте пак след малко.")
NO_REPORT = ("Проверката върху историята още се изчислява (първия път отнема няколко минути), затова още не "
             "казвам колко често печели тази стратегия.")
CONNECT_STEPS = {
    "testnet": ("Отворих прозореца за ключа. Стъпките: отворете app.hyperliquid-testnet.xyz и свържете Phantom "
                "(Connect → Phantom); после More → API — натиснете Generate и одобрете в Phantom; накрая поставете "
                "Ethereum адреса си от Phantom (0x…) и API ключа в прозореца. Никога не поставяйте думите за "
                "възстановяване."),
    "mainnet": ("Отворих прозореца за ключа за ИСТИНСКИ пари. Стъпките: в Phantom внесете пари в Perps баланса; "
                "отворете app.hyperliquid.xyz и свържете Phantom (Connect → Phantom); More → API — Generate и "
                "одобрете в Phantom; поставете Ethereum адреса си от Phantom (0x…) и API ключа в прозореца. Този "
                "ключ може само да търгува — не може да тегли пари, и важи до 180 дни. Никога не поставяйте "
                "думите за възстановяване."),
}
MAINNET_WARNING = ("От сега REAL TRADE търгува с ИСТИНСКИ пари: Орион отваря и затваря сделки сам по проверените "
                   "стратегии. Лимитите остават (2 % риск на сделка, до 10x, до 6 % загуба на ден, до 3 позиции), "
                   "а при спад от 40 % от най-високата стойност на сметката REAL TRADE се спира сам. Загубите ще "
                   "са истински.")


def autopilot_terms(limits) -> str:
    """The body of the dialog before REAL TRADE is switched on by voice."""
    return "\n".join([
        "Орион отваря и затваря сделки сам, без да пита — само по проверените стратегии.",
        f"Риск {limits.risk_pct:g} % на сделка, до {limits.max_leverage}x, до {limits.daily_loss_pct:g} % загуба "
        f"на ден, до {limits.max_positions} позиции.",
        f"Ако сметката падне с {limits.max_drawdown_pct:g} % от най-високата си стойност, REAL TRADE се спира сам.",
        "Стопът и целта на всяка сделка са в борсата.",
    ])


def pct(value: float) -> str:
    return f"{value * 100:.0f} %"


def _move(entry: float, price: float) -> str:
    return f"{(price / entry - 1) * 100:+.1f} %"


def _net(network: str) -> str:
    return "тестовата мрежа" if network == "testnet" else "истинската мрежа"


def period(report: dict | None, coin: str) -> str:
    try:
        entry = report["coins"][coin]
    except (KeyError, TypeError):
        return ""
    start, end = (datetime.fromtimestamp(entry[key] / 1000) for key in ("from", "to"))
    return f"от {start:%m.%Y} до {end:%m.%Y}"


def best(found: list, report: dict | None):
    """The signal to lead with: a strategy that passed the check first, then the strongest."""
    return max(found, key=lambda s: (backtest.is_enabled(report, s.coin, s.strategy), s.strength))


def strategy_line(report: dict | None, coin: str, strategy: str) -> str:
    try:
        st = report["coins"][coin][strategy]
    except (KeyError, TypeError):
        return NO_REPORT
    if not st["trades"]:
        return "В проверката върху историята тази стратегия не е давала сделки за тази монета."
    verdict = "" if backtest.Stats.from_dict(st).enabled else \
        " Стратегията НЕ мина проверката за тази монета, затова не я препоръчвам."
    return (f"В проверката ({period(report, coin)} — период, който настройката не е виждала): {st['trades']} "
            f"сделки, печели {pct(st['win_rate'])} (вероятно между {pct(st['win_low'])} и {pct(st['win_high'])}), "
            f"средно {st['avg_r']:+.2f} пъти риска на сделка след таксите.{verdict}")


def _funding_words(rank: float | None) -> str:
    if rank is None:
        return ""
    if rank >= 0.9:
        return "Финансирането е много високо — мнозина са в лонг."
    if rank <= 0.1:
        return "Финансирането е много ниско — мнозина са в шорт."
    return "Финансирането е нормално."


def _range_hit(report: dict | None, coin: str) -> str:
    try:
        r = report["coins"][coin]["range"]
    except (KeyError, TypeError):
        return ""
    return f" (в проверката такъв диапазон е улучвал {pct(r['hits'] / r['total'])} от дните)" if r["total"] else ""


def forecast(coin: str, found: list, ctx, report: dict | None) -> str:
    lines = [f"{NAMES[coin]}: цена {_fmt(ctx.price)} долара. 4-часовият тренд е {TREND[ctx.trend4]}, "
             f"дневният — {TREND[ctx.trend1d]}."]
    if found:
        lead = best(found, report)
        lines.append(f"Сигнал {SIDE[lead.side]} — {LABELS[lead.strategy]}, сила {lead.strength} от 5. Вход около "
                     f"{_fmt(lead.entry)}, стоп {_fmt(lead.stop)} ({_move(lead.entry, lead.stop)}), цел "
                     f"{_fmt(lead.target)} ({_move(lead.entry, lead.target)}).")
        if len(lead.reasons) > 1:
            lines.append("Защо: " + "; ".join(lead.reasons[1:]) + ".")
        lines.append(strategy_line(report, coin, lead.strategy))
        lines += [f"Има и сигнал {SIDE[s.side]} — {LABELS[s.strategy]}." for s in found if s is not lead]
    else:
        lines.append("Няма ясен сигнал — по-добре е да не се влиза сега.")
        lines.append(f"До 24 часа цената вероятно ще е между {_fmt(ctx.low24)} и {_fmt(ctx.high24)}"
                     f"{_range_hit(report, coin)}.")
        if ctx.support or ctx.resistance:
            lines.append(f"Най-близка подкрепа {_fmt(ctx.support)}, съпротива {_fmt(ctx.resistance)}.")
    funding = _funding_words(ctx.funding_rank)
    if funding:
        lines.append(funding)
    lines.append(NOT_ADVICE)
    return "\n".join(lines)


def signal_line(coin: str, found: list, report: dict | None) -> str:
    if not found:
        return f"{NAMES[coin]}: няма сигнал."
    lead = best(found, report)
    tag = "" if backtest.is_enabled(report, coin, lead.strategy) else " (стратегията не мина проверката)"
    return (f"{NAMES[coin]}: {SIDE[lead.side]} — {LABELS[lead.strategy]}, сила {lead.strength} от 5, вход около "
            f"{_fmt(lead.entry)}, стоп {_fmt(lead.stop)}, цел {_fmt(lead.target)}{tag}.")


def strategy_table(report: dict | None) -> str:
    if not report:
        return NO_REPORT
    lines = ["Проверка на стратегиите върху период, който настройката не е виждала, с таксите и финансирането:"]
    working = 0
    for coin, entry in report["coins"].items():
        parts = []
        for strategy, label in LABELS.items():
            st = entry.get(strategy)
            if not st:
                continue
            if not st["trades"]:
                parts.append(f"{label}: няма сделки")
                continue
            ok = backtest.Stats.from_dict(st).enabled
            working += ok
            parts.append(f"{label}: {st['trades']} сделки, печели {pct(st['win_rate'])}, средно {st['avg_r']:+.2f}R — "
                         f"{'работи' if ok else 'не мина'}")
        lines.append(f"{NAMES.get(coin, coin)} ({period(report, coin)}): " + "; ".join(parts) + ".")
    if not working:
        lines.append("В момента нито една стратегия не мина проверката — честно казано, сега нямам предимство на "
                     "пазара и е по-добре да не се търгува.")
    return "\n".join(lines)


def record_text(summary: dict) -> str:
    days = summary["days"]
    word = "денонощие" if days == 1 else f"{days} дни"
    if not summary["n"]:
        waiting = f" ({summary['open']} чакат резултат)" if summary["open"] else ""
        return f"За последните {word} още няма приключили сигнали{waiting}."
    text = (f"За последните {word}: {summary['n']} приключили сигнала, {summary['wins']} на печалба "
            f"({pct(summary['win_rate'])}), средно {summary['avg_r']:+.2f} пъти риска.")
    parts = [f"{LABELS.get(s, s)} {b['wins']} от {b['n']}" for s, b in summary["by_strategy"].items()]
    if parts:
        text += " По стратегии: " + ", ".join(parts) + "."
    if summary["open"]:
        text += f" Още {summary['open']} чакат резултат."
    return text


def positions_text(state, network: str) -> str:
    if not state.positions:
        return f"Нямате отворени позиции ({_net(network)})."
    parts = [f"{NAMES.get(c, c)} {'лонг' if p['side'] == 'long' else 'шорт'} {p['size']:g} от {_fmt(p['entry'])}, "
             f"сега {p['pnl']:+.2f} $" for c, p in state.positions.items()]
    return f"Отворени позиции ({_net(network)}): " + "; ".join(parts) + "."


def account_text(state, network: str, limits) -> str:
    open_pnl = sum(p["pnl"] for p in state.positions.values())
    return (f"Сметката в {_net(network)}: {state.equity:.2f} долара, отворени позиции {len(state.positions)} "
            f"(сега {open_pnl:+.2f} $), загуба днес {state.lost_today:.2f} $ от лимит "
            f"{state.equity * limits.daily_loss_pct / 100:.2f} $. Риск на сделка {limits.risk_pct:g} %, "
            f"ливъридж до {limits.max_leverage}x.")


def signal_alert(signal, report: dict | None) -> str:
    name = NAMES[signal.coin].lower()
    side = "лонг" if signal.side == "long" else "шорт"
    return (f"Сър, силен сигнал: {SIDE[signal.side]} на {name} — {LABELS[signal.strategy]}, сила {signal.strength} "
            f"от 5. Вход около {_fmt(signal.entry)}, стоп {_fmt(signal.stop)}, цел {_fmt(signal.target)}. "
            f"Кажете „отвори {side} на {name}“, ако искате.")


def fill_text(fill: dict) -> str:
    coin = fill.get("coin", "")
    pnl = float(fill.get("closedPnl") or 0)
    return f"Сър, позицията в {NAMES.get(coin, coin)} се затвори на {_fmt(float(fill['px']))} — {pnl:+.2f} долара."


# --- The autopilot (REAL TRADE) ------------------------------------------------------------------
AUTO_NO_CONNECTION = "Нямам връзка с Hyperliquid — автопилотът ще опита пак след малко."
AUTO_EMPTY = ("Имаше сигнал, но в Perps сметката няма пари — внесете в Perps баланса в Phantom (от SOL или USDC) "
              "и ще търгувам.")


def auto_opened(plan, strategy: str) -> str:
    side = "лонг" if plan.side == "long" else "шорт"
    return (f"Отворих {side} на {NAMES[plan.coin].lower()} — {LABELS.get(strategy, strategy)}: {plan.size:g} "
            f"{plan.coin} (≈ {_fmt(plan.notional)} $), {plan.leverage}x, стоп {_fmt(plan.stop)}, цел "
            f"{_fmt(plan.target)}. Рискът е {plan.risk_usd:.2f} $.")


def auto_skipped(signal, reason: str) -> str:
    side = "лонг" if signal.side == "long" else "шорт"
    return (f"Пропуснах сигнал за {side} на {NAMES[signal.coin].lower()} "
            f"({LABELS.get(signal.strategy, signal.strategy)}): {reason}")


def auto_unchecked(coin: str) -> str:
    return (f"Връзката с борсата прекъсна, докато отварях сделка в {NAMES[coin].lower()}. При следващата проверка "
            f"ще видя дали позицията е отворена и дали има стоп.")


def auto_time_stop(coin: str, side: str) -> str:
    return f"Затварям {'лонг' if side == 'long' else 'шорт'} на {NAMES[coin].lower()} — изтекоха 48 часа."


def account_stop(peak: float, equity: float) -> str:
    fall = (1 - equity / peak) * 100 if peak else 0.0
    return (f"Сър, сметката падна с {fall:.0f} % от най-високата си стойност (от {_fmt(peak)} $ на {_fmt(equity)} $). "
            f"Спрях REAL TRADE — отворените позиции остават със стоповете си. Пуснете бутона пак, когато решите.")


# --- Demo accounts and the simulation -----------------------------------------------------------
_DOLLAR_WORDS = ("", "usd", "$", "долар", "долара", "dollar", "dollars")


def _usd(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ") + " $"


def demo_created(name: str, usd: float, risk_pct: float, all_signals: bool, amount: float, currency: str) -> str:
    money = _usd(usd)
    if currency.strip().lower().rstrip(".") not in _DOLLAR_WORDS:
        money += f" ({amount:,.0f} {currency})".replace(",", " ")
    which = "всички сигнали" if all_signals else "само проверените стратегии"
    return (f"Направих демо сметка „{name}“ с {money} и {risk_pct:g} % риск — {which}. Парите са измислени, "
            f"цените — истински.")


def demo_status(book: dict, mids: dict, on: bool) -> str:
    lines = ["Демо сметките (DEMO TEST е включен — търгувам сам):" if on
             else "Демо сметките (DEMO TEST е изключен — включете го, за да търгувам):"]
    for name, account in book["accounts"].items():
        value = demo.equity(account, mids)
        closed = [t for t in account["closed"] if t.get("status") == "closed"]
        wins = sum(1 for t in closed if t["pnl"] > 0)
        line = (f"„{name}“: {_usd(value)} ({(value / account['start'] - 1) * 100:+.1f} % от {_usd(account['start'])}), "
                f"{len(closed)} приключени сделки, {wins} на печалба")
        if account["open"]:
            line += ", отворени: " + ", ".join(f"{NAMES[t['coin']].lower()} {'лонг' if t['side'] == 'long' else 'шорт'}"
                                               for t in account["open"])
        if name == demo.active(book):
            line += " (избрана)"
        lines.append(line + ".")
    return "\n".join(lines)


def demo_opened(name: str, trade: dict) -> str:
    side = "лонг" if trade["side"] == "long" else "шорт"
    return (f"DEMO „{name}“: отворих {side} на {NAMES[trade['coin']].lower()} на {_fmt(trade['entry'])}, стоп "
            f"{_fmt(trade['stop'])}, цел {_fmt(trade['target'])}, размер {trade['size']:.4g}. Без истински пари.")


def demo_closed(name: str, trades: list[dict], account: dict) -> str:
    parts = ", ".join(f"{NAMES[t['coin']].lower()} ({t['pnl']:+.2f} $)" for t in trades)
    return f"DEMO „{name}“: затворих {parts}. Балансът е {_usd(account['balance'])}."


def simulation(result, risk_pct: float, all_signals: bool) -> str:
    used = [f"{LABELS[s]} на {NAMES[c].lower()}" for c, names in result.strategies.items() for s in names]
    if not used:
        return ("Нито една стратегия не мина проверката, затова няма какво да симулирам. Кажете „симулирай … с "
                "всички сигнали“, за да видите и непроверените.")
    which = "всички стратегии" if all_signals else "проверените стратегии (" + ", ".join(used) + ")"
    text = (f"Симулация за последните {result.days} дни с {_usd(result.start)} и {risk_pct:g} % риск, {which}: "
            f"накрая {_usd(result.final)} ({result.return_pct:+.1f} %). {result.trades} сделки, {result.wins} на "
            f"печалба. Най-голямо падане {result.max_drawdown_pct:.1f} %.")
    if result.months:
        best_month = max(result.months.items(), key=lambda kv: kv[1])
        worst_month = min(result.months.items(), key=lambda kv: kv[1])
        text += (f" Най-добър месец {best_month[0]} ({best_month[1]:+.1f} %), най-лош {worst_month[0]} "
                 f"({worst_month[1]:+.1f} %).")
    return text + " Миналото не гарантира бъдещето."
