"""
The strategy lab (test mode): tries other numbers for one strategy at a time. A variant replaces the
current numbers only through two gates — (a) on the history it beats them on the 30 % no tuning saw and
passes the enable rule, then (b) it also beats them over its first 20 practice trades, run side by side.
Only numbers change; code changes still need „Одобри и включи“.
"""
import itertools
import json
import time
from dataclasses import asdict

from . import COINS, MEMORY, backtest, market, signals
from .signals import LABELS, STRATEGIES

LAB = MEMORY / "trading_lab.json"
TRIAL_TRADES = 20
MARGIN = 0.10              # a variant must beat the average R by 10 % (and by at least 0.02 R)
SEARCH_EVERY_DAYS = 7      # the history changes slowly — the same search again is wasted work
GRIDS = {
    "pullback": {"fast": [13, 21], "slow": [55, 89], "stop_atr": [1.0, 1.5, 2.0], "reward": [2.0, 2.5]},
    "breakout": {"channel": [20, 48], "volume": [1.3, 1.5, 2.0], "stop_atr": [1.5, 2.0], "reward": [2.0, 2.5]},
    "reversal": {"funding_pct": [0.9, 0.95, 0.98], "rsi": [70, 75, 80], "stop_atr": [1.5, 2.0]},
}


def load() -> dict:
    try:
        saved = json.loads(LAB.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {"candidates": saved.get("candidates", {}), "log": saved.get("log", []), "searched": saved.get("searched", {})}


def save(state: dict) -> None:
    state["log"] = state["log"][-200:]
    LAB.parent.mkdir(parents=True, exist_ok=True)
    LAB.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def candidates() -> dict[str, dict]:
    """The numbers on trial now {strategy: numbers} — the practice account trades them as „candidate“."""
    return {strategy: c["params"] for strategy, c in load()["candidates"].items()}


def variants(strategy: str, current: dict) -> list[dict]:
    grid = GRIDS[strategy]
    found = []
    for combo in itertools.product(*grid.values()):
        numbers = {**current, **dict(zip(grid, combo))}
        if numbers != current:
            found.append(numbers)
    return found


def better(new_r: float, old_r: float) -> bool:
    return new_r > old_r + max(MARGIN * abs(old_r), 0.02)


def _trades(markets_by_coin: dict, params: dict, strategy: str, part: str) -> list:
    trades = []
    for p in markets_by_coin.values():
        q = signals.with_params(p, params)
        cut = int(len(q.h1) * backtest.SPLIT)
        start, end = (signals.WARMUP, cut) if part == "tune" else (cut, len(q.h1))
        trades += backtest.simulate(q, strategy, start, end)
    return trades


def search(strategy: str, markets_by_coin: dict):
    """Gate (a): the best variant on the tuning 70 %, then it and the current numbers judged on the other 30 %."""
    current = signals.load_params()
    best, best_total = None, None
    for numbers in variants(strategy, current[strategy]):
        total = sum(t.r for t in _trades(markets_by_coin, {**current, strategy: numbers}, strategy, "tune"))
        if best_total is None or total > best_total:
            best, best_total = numbers, total
    if best is None:
        return None
    new = backtest.stats(_trades(markets_by_coin, {**current, strategy: best}, strategy, "test"))
    old = backtest.stats(_trades(markets_by_coin, current, strategy, "test"))
    return best, new, old


def _mean_r(trades: list[dict]) -> float:
    return sum(t["r"] for t in trades) / len(trades) if trades else 0.0


def step(practice_state: dict, log=print, markets_by_coin: dict | None = None) -> str:
    """Judges finished trials (gate b), then starts one new search (gate a). Returns what changed."""
    state = load()
    notes = []
    now = int(time.time() * 1000)
    for strategy, trial in list(state["candidates"].items()):
        def mine(variant):
            return [t for t in practice_state["closed"] if t.get("status") == "closed" and t["strategy"] == strategy
                    and t["variant"] == variant and t["time"] >= trial["since"]]
        tried = mine("candidate")
        if len(tried) < TRIAL_TRADES:
            continue
        new_r, old_r = _mean_r(tried), _mean_r(mine("current"))
        promoted = better(new_r, old_r)
        if promoted:
            signals.save_params(strategy, trial["params"], f"лабораторията: {len(tried)} тренировъчни сделки, "
                                                            f"{new_r:+.2f}R срещу {old_r:+.2f}R")
            notes.append(f"нови числа за „{LABELS[strategy]}“ — минаха и двете проверки")
        else:
            notes.append(f"вариантът за „{LABELS[strategy]}“ не издържа тренировката — оставям старите числа")
        state["log"].append({"time": now, "strategy": strategy, "params": trial["params"], "promoted": promoted,
                             "new_r": new_r, "old_r": old_r})
        del state["candidates"][strategy]
    week = SEARCH_EVERY_DAYS * 24 * 3_600_000
    free = [s for s in STRATEGIES if s not in state["candidates"] and now - state["searched"].get(s, 0) >= week]
    if free:  # the strategy searched longest ago goes first (STRATEGIES order on the first run)
        strategy = min(free, key=lambda s: state["searched"].get(s, 0))
        state["searched"][strategy] = now
        if markets_by_coin is None:
            markets_by_coin = {coin: market.history(coin) for coin in COINS}
        found = search(strategy, markets_by_coin)
        if found:
            numbers, new, old = found
            if new.enabled and better(new.avg_r, old.avg_r):
                state["candidates"][strategy] = {"params": numbers, "since": now, "oos": asdict(new)}
                notes.append(f"пробвам нови числа за „{LABELS[strategy]}“ в тренировката")
                log(f"Лаборатория: {LABELS[strategy]} {numbers} — {new.avg_r:+.2f}R срещу {old.avg_r:+.2f}R")
    save(state)
    return "; ".join(notes)
