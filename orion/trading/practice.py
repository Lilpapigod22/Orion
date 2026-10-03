"""
The practice account — the strategy lab's exercise (DEMO TEST). $10 000 of virtual money: every signal of
every strategy (and of the lab's candidate numbers) is opened without asking on the demo engine — one
position per coin, strategy and variant, so every signal is measured — and settled from the candles with
the backtest's costs. Nothing here touches the exchange; the watch runs the daily minimum-size TESTNET order
check when testnet_due() says so.
"""
import json
import threading
import time
from dataclasses import dataclass, field

from . import MEMORY, demo, journal, lab, settings, signals

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


def open_signals(state: dict, found: list, variant: str, limits) -> int:
    """A virtual trade for every new signal — one per coin, strategy and variant at a time."""
    return len(demo.open_signals(state, found, variant, limits, per_coin=False))


settle = demo.settle
by_strategy = demo.by_strategy


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


def step(prepared_by_coin: dict) -> Round:
    """Settles, opens the new signals (current + lab candidates) and judges finished trials. Quick: files and
    the candles the watch already fetched."""
    with _lock:
        state = load()
        limits = settings.limits()
        closed = settle(state, {c: p.h1 for c, p in prepared_by_coin.items()},
                        {c: (p.funding_t, p.funding_v) for c, p in prepared_by_coin.items()})
        opened = 0
        on_trial = lab.candidates()
        for p in prepared_by_coin.values():
            found = signals.latest(p)
            for s in found:
                journal.add_signal(s, "practice")
            opened += open_signals(state, found, "current", limits)
            for strategy, numbers in on_trial.items():
                trial = signals.with_params(p, {**p.params, strategy: numbers})
                opened += open_signals(state, signals.signals_at(trial, len(trial.h1) - 1, only=strategy),
                                       "candidate", limits)
        note = lab.judge(state)
        save(state)
        return Round(state["balance"], state["start"], opened, closed, by_strategy(state), note)


def testnet_due() -> bool:
    """The daily minimum-size order check on the TESTNET — only with a testnet key."""
    return time.time() - load()["testnet_check"] >= TESTNET_EVERY_HOURS * 3600 and bool(settings.account("testnet"))


def mark_testnet() -> None:
    with _lock:
        state = load()
        state["testnet_check"] = time.time()
        save(state)
