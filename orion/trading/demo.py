"""
Demo accounts — virtual money on live Hyperliquid prices (memory/trading_demo.json). Several named accounts
trade the same signals, each with its own risk; while DEMO TEST is on the watch opens and settles their
trades by itself — no approval, the money does not exist. Trades are settled exactly like the backtest
(fees, slippage, hourly funding; a candle touching the stop and the target counts as the stop). Demo
accounts hold one position per coin, as on the exchange. The strategy lab's practice account uses the same
engine with one position per coin, strategy and variant, so every signal is measured.
"""
import json
import threading
import time
import urllib.request
from bisect import bisect_left

from ..markets import _fmt
from . import MEMORY, NAMES, backtest, data, signals
from .risk import Limits

DEMO_FILE = MEMORY / "trading_demo.json"
BGN_PER_EUR = 1.95583
MIN_BALANCE = 10.0
SIDE_WORD = {"long": "лонг", "short": "шорт"}
_lock = threading.RLock()


def _now() -> int:
    return int(time.time() * 1000)


# --- The book of accounts ------------------------------------------------------------------------
def load() -> dict:
    try:
        saved = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {"accounts": saved.get("accounts", {}), "active": saved.get("active")}


def save(book: dict) -> None:
    for account in book["accounts"].values():
        account["closed"] = account["closed"][-2000:]
    DEMO_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEMO_FILE.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")


def new_account(balance: float, risk_pct: float = 2.0, all_signals: bool = False) -> dict:
    return {"start": balance, "balance": balance, "risk_pct": risk_pct, "all_signals": all_signals,
            "created": _now(), "open": [], "closed": []}


def _eur_per_usd() -> float:
    request = urllib.request.Request("https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR",
                                     headers={"User-Agent": data.USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        return float(json.load(response)["rates"]["EUR"])


def to_usd(amount: float, currency: str) -> float:
    """Demo accounts are in dollars: лева and евро are converted at today's rate (the лев is pegged to the euro)."""
    word = currency.strip().lower().rstrip(".")
    if word in ("", "usd", "$", "долар", "долара", "dollar", "dollars"):
        return float(amount)
    if word in ("bgn", "лв", "лев", "лева"):
        return float(amount) / BGN_PER_EUR / _eur_per_usd()
    if word in ("eur", "евро", "€"):
        return float(amount) / _eur_per_usd()
    raise ValueError("Кажете сумата в долари, лева или евро.")


def find(book: dict, text: str) -> str | None:
    """The account sir means: the exact name, else a name inside what he said (case does not matter)."""
    wanted = text.strip().strip("„“\"'").lower()
    if not wanted:
        return None
    for name in book["accounts"]:
        if name.lower() == wanted:
            return name
    for name in sorted(book["accounts"], key=len, reverse=True):
        if name.lower() in wanted:
            return name
    return None


def active(book: dict) -> str | None:
    if book.get("active") in book["accounts"]:
        return book["active"]
    return next(iter(book["accounts"]), None)


def _next_name(book: dict) -> str:
    k = 1
    while f"демо {k}" in book["accounts"]:
        k += 1
    return f"демо {k}"


def create(name: str, balance: float, risk_pct: float = 2.0, all_signals: bool = False) -> str:
    if balance < MIN_BALANCE:
        raise ValueError(f"Демо сметката трябва да е поне {MIN_BALANCE:.0f} долара.")
    if not 0 < risk_pct <= 10:
        raise ValueError("Рискът на сделка трябва да е между 0,1 и 10 %.")
    with _lock:
        book = load()
        name = name.strip().strip("„“\"'") or _next_name(book)
        if name in book["accounts"]:
            raise ValueError(f"Вече има демо сметка „{name}“. Изберете друго име или я започнете отначало.")
        book["accounts"][name] = new_account(round(float(balance), 2), float(risk_pct), bool(all_signals))
        book["active"] = name
        save(book)
    return name


def _must_find(book: dict, text: str) -> str:
    name = find(book, text)
    if not name:
        raise ValueError(f"Няма демо сметка „{text.strip()}“.")
    return name


def delete(text: str) -> str:
    with _lock:
        book = load()
        name = _must_find(book, text)
        del book["accounts"][name]
        if book["active"] == name:
            book["active"] = next(iter(book["accounts"]), None)
        save(book)
    return name


def reset(text: str = "") -> list[str]:
    """The same start and risk, the trades cleared — one account, or all of them when no name is given."""
    with _lock:
        book = load()
        if not book["accounts"]:
            raise ValueError("Нямате демо сметки — кажете „направи демо сметка с 1000 долара“.")
        names = [_must_find(book, text)] if text.strip() else list(book["accounts"])
        for name in names:
            old = book["accounts"][name]
            book["accounts"][name] = new_account(old["start"], old["risk_pct"], old["all_signals"])
        save(book)
    return names


def choose(text: str) -> str:
    with _lock:
        book = load()
        name = _must_find(book, text)
        book["active"] = name
        save(book)
    return name


# --- The engine (demo accounts and the practice account) ---------------------------------------
def open_signals(account: dict, found: list, variant: str = "current", limits: Limits | None = None,
                 per_coin: bool = True) -> list[dict]:
    """A virtual trade for every new signal, sized to lose the account's risk % at the stop (capped by the
    leverage limit). Returns the trades opened."""
    limits = limits or Limits()
    risk_pct = account.get("risk_pct", limits.risk_pct)
    opened = []
    for s in found:
        if any(t["coin"] == s.coin and (per_coin or (t["strategy"], t["variant"]) == (s.strategy, variant))
               for t in account["open"]):
            continue
        if any((t["coin"], t["strategy"], t["variant"], t["time"]) == (s.coin, s.strategy, variant, s.time)
               for t in account["closed"][-300:]):
            continue
        size = min(account["balance"] * risk_pct / 100 / s.risk, account["balance"] * limits.max_leverage / s.entry)
        trade = {**s.to_dict(), "variant": variant, "size": size}
        account["open"].append(trade)
        opened.append(trade)
    return opened


def _close(account: dict, trade: dict, price: float, exit_time: int, why: str, funding: tuple) -> dict:
    times, rates = funding
    paid = backtest.funding_cost(trade["side"], times, rates, trade["time"], exit_time)
    r = backtest.result_r(trade["coin"], trade["side"], trade["entry"], price, trade["stop"], paid)
    pnl = r * trade["size"] * abs(trade["entry"] - trade["stop"])
    account["balance"] += pnl
    trade.update(status="closed", exit=price, exit_time=exit_time, why=why, r=round(r, 3), pnl=round(pnl, 2))
    account["open"].remove(trade)
    account["closed"].append(trade)
    return trade


def settle(account: dict, bars_by_coin: dict, funding_by_coin: dict) -> list[dict]:
    """Closes trades at their stop, target or 48 h; trades older than the candles we have expire."""
    closed = []
    for trade in list(account["open"]):
        bars = bars_by_coin.get(trade["coin"])
        if bars is None or not len(bars):
            continue
        if trade["time"] < bars.t[0]:  # Orion was off for longer than the candle window
            account["open"].remove(trade)
            trade["status"] = "expired"
            account["closed"].append(trade)
            continue
        done = backtest.exit_walk(trade["side"], trade["stop"], trade["target"], bars,
                                  bisect_left(bars.t, trade["time"]),
                                  trade["time"] + signals.TIME_STOP_HOURS * data.HOUR)
        if done:
            k, price, why = done
            closed.append(_close(account, trade, price, bars.end(k), why,
                                 funding_by_coin.get(trade["coin"], ([], []))))
    return closed


def open_manual(account: dict, coin: str, side: str, entry: float, stop: float, target: float, strategy: str,
                limits: Limits | None = None) -> dict:
    """„Отвори лонг на биткойн“ in the demo: at the current price, sized like a signal."""
    if any(t["coin"] == coin for t in account["open"]):
        raise ValueError(f"В демото вече има позиция в {NAMES[coin]}. Първо я затворете.")
    signal = signals.Signal(coin, strategy, side, _now(), entry, stop, target, 0, [])
    return open_signals(account, [signal], "manual", limits)[0]


def close_manual(account: dict, coin: str, price: float) -> list[dict]:
    """„Затвори биткойна“ in the demo: at the current price (funding at Hyperliquid's baseline rate)."""
    return [_close(account, t, price, _now(), "ръчно", ([], [])) for t in list(account["open"]) if t["coin"] == coin]


def by_strategy(account: dict, variant: str = "current") -> dict:
    out: dict[str, dict] = {}
    for t in account["closed"]:
        if t.get("status") != "closed" or t["variant"] != variant:
            continue
        entry = out.setdefault(t["strategy"], {"n": 0, "wins": 0, "r": 0.0})
        entry["n"] += 1
        entry["wins"] += t["r"] > 0
        entry["r"] += t["r"]
    return out


def equity(account: dict, mids: dict) -> float:
    """The balance plus the open trades valued at the current prices (before closing costs)."""
    value = account["balance"]
    for t in account["open"]:
        if t["coin"] in mids:
            sign = 1 if t["side"] == "long" else -1
            value += sign * (mids[t["coin"]] - t["entry"]) * t["size"]
    return value


def step(book: dict, prepared_by_coin: dict, report: dict | None) -> list[str]:
    """DEMO TEST: settles and opens the trades of every account. Returns the journal lines."""
    lines = []
    bars = {coin: p.h1 for coin, p in prepared_by_coin.items()}
    funding = {coin: (p.funding_t, p.funding_v) for coin, p in prepared_by_coin.items()}
    latest = {coin: signals.latest(p) for coin, p in prepared_by_coin.items()}
    for name, account in book["accounts"].items():
        for t in settle(account, bars, funding):
            lines.append(f"DEMO {name}: затворих {SIDE_WORD[t['side']]} на {NAMES[t['coin']].lower()} "
                         f"({t['why']}): {t['pnl']:+.2f} $.")
        for coin, found in latest.items():
            allowed = [s for s in found if account["all_signals"] or backtest.is_enabled(report, coin, s.strategy)]
            for t in open_signals(account, allowed):
                lines.append(f"DEMO {name}: отворих {SIDE_WORD[t['side']]} на {NAMES[t['coin']].lower()} — "
                             f"{signals.LABELS[t['strategy']]}, стоп {_fmt(t['stop'])}, цел {_fmt(t['target'])}.")
    return lines
