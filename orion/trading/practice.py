"""
The practice account — test mode's main exercise. $10 000 of virtual money: every signal of every strategy
(and of the lab's candidate numbers) is opened without asking, sized like a real trade (2 % risk, leverage
cap), on live Hyperliquid prices, and settled from the candles with the backtest's costs. The position-count
limit is not applied, so every signal is measured. Nothing here touches the exchange — except the daily
minimum-size order check on the TESTNET.
"""
import json
import threading
import time
from bisect import bisect_left
from dataclasses import dataclass, field

from . import COINS, MEMORY, backtest, data, exchange, journal, lab, market, risk, settings, signals

PRACTICE = MEMORY / "trading_practice.json"
START = 10_000.0
TESTNET_EVERY_HOURS = 24
_lock = threading.Lock()


def load() -> dict:
    try:
        saved = json.loads(PRACTICE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {"balance": saved.get("balance", START), "start": saved.get("start", START),
            "open": saved.get("open", []), "closed": saved.get("closed", []),
            "testnet_check": saved.get("testnet_check", 0)}


def save(state: dict) -> None:
    state["closed"] = state["closed"][-2000:]
    PRACTICE.parent.mkdir(parents=True, exist_ok=True)
    PRACTICE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def open_signals(state: dict, found: list, variant: str, limits: risk.Limits) -> int:
    """A virtual trade for every new signal — one per coin, strategy and variant at a time."""
    opened = 0
    for s in found:
        key = (s.coin, s.strategy, variant)
        if any((t["coin"], t["strategy"], t["variant"]) == key for t in state["open"]):
            continue
        if any((t["coin"], t["strategy"], t["variant"], t["time"]) == (*key, s.time) for t in state["closed"][-300:]):
            continue
        size = min(risk.size_for(state["balance"], s.entry, s.stop, limits),
                   state["balance"] * limits.max_leverage / s.entry)
        state["open"].append({**s.to_dict(), "variant": variant, "size": size})
        opened += 1
    return opened


def settle(state: dict, bars_by_coin: dict, funding_by_coin: dict) -> list[dict]:
    """Closes virtual trades at their stop, target or 48 h; trades older than the candles expire."""
    closed = []
    for t in list(state["open"]):
        bars = bars_by_coin.get(t["coin"])
        if bars is None or not len(bars):
            continue
        if t["time"] < bars.t[0]:  # Orion was off for longer than the candle window
            state["open"].remove(t)
            t["status"] = "expired"
            state["closed"].append(t)
            continue
        done = backtest.exit_walk(t["side"], t["stop"], t["target"], bars, bisect_left(bars.t, t["time"]),
                                  t["time"] + signals.TIME_STOP_HOURS * data.HOUR)
        if not done:
            continue
        k, price, why = done
        times, rates = funding_by_coin.get(t["coin"], ([], []))
        paid = backtest.funding_cost(t["side"], times, rates, t["time"], bars.end(k))
        r = backtest.result_r(t["coin"], t["side"], t["entry"], price, t["stop"], paid)
        pnl = r * t["size"] * abs(t["entry"] - t["stop"])
        state["balance"] += pnl
        t.update(status="closed", exit=price, exit_time=bars.end(k), why=why, r=round(r, 3), pnl=round(pnl, 2))
        state["open"].remove(t)
        state["closed"].append(t)
        closed.append(t)
    return closed


def by_strategy(state: dict, variant: str = "current") -> dict:
    out: dict[str, dict] = {}
    for t in state["closed"]:
        if t.get("status") != "closed" or t["variant"] != variant:
            continue
        entry = out.setdefault(t["strategy"], {"n": 0, "wins": 0, "r": 0.0})
        entry["n"] += 1
        entry["wins"] += t["r"] > 0
        entry["r"] += t["r"]
    return out


@dataclass
class Round:
    balance: float
    start: float
    opened: int
    closed: list[dict] = field(default_factory=list)
    by_strategy: dict = field(default_factory=dict)
    lab_note: str = ""
    testnet_note: str = ""

    def summary(self) -> str:
        change = (self.balance / self.start - 1) * 100
        text = f"тренировъчната сметка е {self.balance:,.0f} $ ({change:+.1f} %)".replace(",", " ")
        n = sum(b["n"] for b in self.by_strategy.values())
        if n:
            text += f", {n} приключили сделки, {sum(b['wins'] for b in self.by_strategy.values())} на печалба"
        if self.lab_note:
            text += f"; {self.lab_note}"
        if self.testnet_note:
            text += f"; {self.testnet_note[0].lower()}{self.testnet_note[1:].rstrip('.')}"
        return text


def run(log=print) -> Round:
    """One test-mode trading stage: settle, open the new signals (current + lab candidates), one lab step,
    and the daily testnet order check."""
    with _lock:
        state = load()
        limits = settings.limits()
        prepared = {coin: market.live(coin) for coin in COINS}
        closed = settle(state, {c: p.h1 for c, p in prepared.items()},
                        {c: (p.funding_t, p.funding_v) for c, p in prepared.items()})
        opened = 0
        on_trial = lab.candidates()
        for coin, p in prepared.items():
            found = signals.latest(p)
            for s in found:
                journal.add_signal(s, "practice")
            opened += open_signals(state, found, "current", limits)
            for strategy, numbers in on_trial.items():
                trial = signals.with_params(p, {**p.params, strategy: numbers})
                opened += open_signals(state, signals.signals_at(trial, len(trial.h1) - 1, only=strategy),
                                       "candidate", limits)
        lab_note = lab.step(state, log)
        testnet_note = ""
        if time.time() - state["testnet_check"] >= TESTNET_EVERY_HOURS * 3600 and settings.account("testnet"):
            state["testnet_check"] = time.time()
            try:
                testnet_note = exchange.testnet_check()
            except Exception as e:  # noqa: BLE001 — reported, never fatal
                testnet_note = f"Проверката в тестовата мрежа не мина: {e}"
        save(state)
        return Round(state["balance"], state["start"], opened, closed, by_strategy(state), lab_note, testnet_note)
