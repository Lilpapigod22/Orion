"""
The live record: every signal Orion gives (asked, watched, practised) and every real trade, with the
outcome settled later from Hyperliquid's 1h candles — so „колко позна“ has a real answer. Signal results
are in R after fees and slippage (funding over ≤48 h is left out: a few hundredths of an R).
"""
import json
import threading
import time
from bisect import bisect_left

from . import MEMORY, backtest, data, signals

JOURNAL = MEMORY / "trading_journal.json"
LIMIT = 3000
_lock = threading.RLock()


def _load() -> list[dict]:
    try:
        items = json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return items if isinstance(items, list) else []


def _save(items: list[dict]) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(items[-LIMIT:], ensure_ascii=False), encoding="utf-8")


def _now() -> int:
    return int(time.time() * 1000)


def add_signal(signal: signals.Signal, source: str) -> bool:
    """Records a signal once — the same coin, strategy, side and candle are not repeated."""
    with _lock:
        items = _load()
        key = (signal.coin, signal.strategy, signal.side, signal.time)
        if any(e.get("kind") == "signal" and (e["coin"], e["strategy"], e["side"], e["time"]) == key for e in items):
            return False
        items.append({"kind": "signal", "source": source, "status": "open", **signal.to_dict()})
        _save(items)
        return True


def add_trade(plan, strategy: str, auto: bool = False) -> None:
    """A real trade (the network is its source): sir approved it, or the autopilot opened it (auto)."""
    with _lock:
        items = _load()
        items.append({"kind": "trade", "source": plan.network, "status": "open", "coin": plan.coin,
                      "side": plan.side, "strategy": strategy, "entry": plan.entry, "stop": plan.stop,
                      "target": plan.target, "size": plan.size, "time": _now(), "auto": bool(auto)})
        _save(items)


def open_trades() -> list[dict]:
    """The real trades still open, oldest first."""
    with _lock:
        return [e for e in _load() if e.get("kind") == "trade" and e["status"] == "open"]


def close_trade(coin: str, exit_price: float | None = None, pnl: float | None = None) -> None:
    with _lock:
        items = _load()
        for e in items:
            if e.get("kind") == "trade" and e["coin"] == coin and e["status"] == "open":
                e.update(status="closed", exit=exit_price, pnl=pnl, exit_time=_now())
        _save(items)


def open_trade_time(coin: str) -> int | None:
    """When Orion opened the real trade that is still open in this coin (ms)."""
    with _lock:
        times = [e["time"] for e in _load()
                 if e.get("kind") == "trade" and e["coin"] == coin and e["status"] == "open"]
    return max(times) if times else None


def resolve(bars_for=None) -> int:
    """Settles open signals whose stop, target or 48 h has passed. Returns how many were settled."""
    bars_for = bars_for or (lambda coin: data.live_bars(coin, "1h", 1000))
    with _lock:
        items = _load()
        waiting = [e for e in items if e.get("kind") == "signal" and e["status"] == "open"]
        settled = 0
        for coin in sorted({e["coin"] for e in waiting}):
            bars = bars_for(coin)
            if not len(bars):
                continue
            for e in (w for w in waiting if w["coin"] == coin):
                if e["time"] < bars.t[0]:  # older than the candles we have — cannot be judged any more
                    e["status"] = "expired"
                    settled += 1
                    continue
                deadline = e["time"] + signals.TIME_STOP_HOURS * data.HOUR
                done = backtest.exit_walk(e["side"], e["stop"], e["target"], bars, bisect_left(bars.t, e["time"]),
                                          deadline)
                if done:
                    k, price, why = done
                    e.update(status="closed", exit=price, exit_time=bars.end(k), why=why,
                             r=round(backtest.result_r(coin, e["side"], e["entry"], price, e["stop"], 0.0), 3))
                    settled += 1
        if settled:
            _save(items)
        return settled


def record(days: int = 7, now_ms: int | None = None) -> dict:
    """How the signals of the last `days` days did (all sources)."""
    since = (now_ms or _now()) - days * 24 * data.HOUR
    with _lock:
        items = _load()
    closed = [e for e in items
              if e.get("kind") == "signal" and e["status"] == "closed" and e.get("exit_time", 0) >= since]
    by_strategy: dict[str, dict] = {}
    for e in closed:
        entry = by_strategy.setdefault(e["strategy"], {"n": 0, "wins": 0, "r": 0.0})
        entry["n"] += 1
        entry["wins"] += e["r"] > 0
        entry["r"] += e["r"]
    n = len(closed)
    wins = sum(1 for e in closed if e["r"] > 0)
    return {"days": days, "n": n, "wins": wins, "win_rate": wins / n if n else 0.0,
            "avg_r": sum(e["r"] for e in closed) / n if n else 0.0,
            "open": sum(1 for e in items if e.get("kind") == "signal" and e["status"] == "open"),
            "by_strategy": by_strategy}
