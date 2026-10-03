"""
The honest check: every strategy is replayed candle by candle on years of history, with fees, slippage
and hourly funding. The lab tunes numbers only on the first 70 % of the history; everything Orion reports
comes from the last 30 %, which no tuning saw. Run by hand: `python -m orion.trading.backtest`.
"""
import json
import math
import threading
import time
from bisect import bisect_right
from dataclasses import asdict, dataclass

from . import COINS, MEMORY, data, market, signals
from .data import Bars

STATS_FILE = MEMORY / "trading_stats.json"
FEE = 0.00045                                         # Hyperliquid taker fee per side (base tier)
SLIPPAGE = {"BTC": 0.0002, "ETH": 0.0003, "SOL": 0.0005}
SPLIT = 0.7
MIN_TRADES, MIN_PROFIT_FACTOR = 30, 1.1
MAX_AGE_DAYS = 7
PF_CAP = 99.0
_running = threading.Event()
# app.py sets it to test mode's sandbox lock: the background report is written only outside the sandbox.
save_lock = None  # a threading.Lock, or None


@dataclass
class Trade:
    coin: str
    strategy: str
    side: str
    entry_time: int
    exit_time: int
    entry: float
    exit: float
    stop: float
    target: float
    r: float            # the result in multiples of the risk, after costs
    why: str            # "стоп" | "цел" | "време"


def exit_walk(side: str, stop: float, target: float, bars: Bars, start: int,
              deadline: int) -> tuple[int, float, str] | None:
    """From candle `start` on: (index, exit price, why) at the stop, the target or the time stop; None while
    the trade is still open. A candle touching both counts as the stop; a gap past a level exits at the open."""
    for k in range(start, len(bars)):
        if side == "long":
            if bars.l[k] <= stop:
                return k, min(stop, bars.o[k]), "стоп"
            if bars.h[k] >= target:
                return k, max(target, bars.o[k]), "цел"
        else:
            if bars.h[k] >= stop:
                return k, max(stop, bars.o[k]), "стоп"
            if bars.l[k] <= target:
                return k, min(target, bars.o[k]), "цел"
        if bars.end(k) >= deadline:
            return k, bars.c[k], "време"
    return None


def funding_cost(side: str, funding_t: list[int], funding_v: list[float], start: int, end: int) -> float:
    """What holding cost in funding, as a fraction of the position's value (negative: it earned)."""
    lo, hi = bisect_right(funding_t, start), bisect_right(funding_t, end)
    if hi > lo:
        paid = sum(funding_v[lo:hi])
    else:
        paid = data.DEFAULT_FUNDING * max(0, round((end - start) / data.HOUR))
    return paid if side == "long" else -paid


def result_r(coin: str, side: str, entry: float, exit_price: float, stop: float, funding_paid: float) -> float:
    """The trade's result in R (multiples of the risk) after fees, slippage and funding."""
    sign = 1 if side == "long" else -1
    net = sign * (exit_price - entry) / entry - 2 * (FEE + SLIPPAGE[coin]) - funding_paid
    return net / (abs(entry - stop) / entry)


def simulate(p: signals.Prepared, strategy: str, start: int, end: int) -> list[Trade]:
    """One strategy, one position at a time, entries at the next candle's open, for signals in [start, end)."""
    trades, i = [], max(start, signals.WARMUP)
    while i < end - 1:
        found = signals.signals_at(p, i, only=strategy)
        if not found:
            i += 1
            continue
        s = found[0]
        k = i + 1
        entry = p.h1.o[k]
        if not (s.stop < entry < s.target if s.side == "long" else s.target < entry < s.stop):
            i += 1  # the next candle opened past a level — no trade
            continue
        done = exit_walk(s.side, s.stop, s.target, p.h1, k, p.h1.t[k] + signals.TIME_STOP_HOURS * data.HOUR)
        if done is None:
            break  # still open when the data ends
        x, price, why = done
        paid = funding_cost(s.side, p.funding_t, p.funding_v, p.h1.t[k], p.h1.end(x))
        trades.append(Trade(p.coin, strategy, s.side, p.h1.t[k], p.h1.end(x), entry, price, s.stop, s.target,
                            result_r(p.coin, s.side, entry, price, s.stop, paid), why))
        i = x + 1
    return trades


@dataclass
class Stats:
    trades: int
    win_rate: float
    win_low: float           # 95 % Wilson interval of the win rate
    win_high: float
    avg_r: float
    profit_factor: float
    max_drawdown_r: float

    @property
    def enabled(self) -> bool:
        return self.trades >= MIN_TRADES and self.avg_r > 0 and self.profit_factor >= MIN_PROFIT_FACTOR

    @classmethod
    def from_dict(cls, saved: dict) -> "Stats":
        return cls(**{name: saved[name] for name in cls.__dataclass_fields__})


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / d, (centre + margin) / d


def stats(trades: list[Trade]) -> Stats:
    n = len(trades)
    if not n:
        return Stats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    wins = sum(1 for t in trades if t.r > 0)
    gains = sum(t.r for t in trades if t.r > 0)
    losses = -sum(t.r for t in trades if t.r < 0)
    peak = total = drawdown = 0.0
    for t in trades:
        total += t.r
        peak = max(peak, total)
        drawdown = max(drawdown, peak - total)
    low, high = wilson(wins, n)
    return Stats(n, wins / n, low, high, sum(t.r for t in trades) / n,
                 min(gains / losses, PF_CAP) if losses else PF_CAP, drawdown)


def range_hits(p: signals.Prepared, start: int, end: int) -> tuple[int, int]:
    """How often the 24 h range forecast held: (inside, days checked)."""
    hits = total = 0
    for i in range(max(start, 24 * 30), end - 24, 24):
        low, high = signals.range_24h(p.h1, i)
        total += 1
        hits += low <= p.h1.c[i + 24] <= high
    return hits, total


def run(coins=COINS, params: dict | None = None, save: bool = True) -> dict:
    """Backtests every strategy on every coin (reported on the last 30 %), saves and returns the report."""
    report = {"time": int(time.time() * 1000), "coins": {}}
    for coin in coins:
        p = market.history(coin, params)
        cut = int(len(p.h1) * SPLIT)
        entry = {name: asdict(stats(simulate(p, name, cut, len(p.h1)))) for name in signals.STRATEGIES}
        hits, total = range_hits(p, cut, len(p.h1))
        entry.update(range={"hits": hits, "total": total}, **{"from": p.h1.t[cut], "to": p.h1.end(len(p.h1) - 1)})
        report["coins"][coin] = entry
    if save:
        _save(report)
    return report


def _save(report: dict) -> None:
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def load() -> dict | None:
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def stale() -> bool:
    report = load()
    return not report or time.time() * 1000 - report["time"] > MAX_AGE_DAYS * 24 * data.HOUR


def is_enabled(report: dict | None, coin: str, strategy: str) -> bool:
    try:
        return Stats.from_dict(report["coins"][coin][strategy]).enabled
    except (KeyError, TypeError):
        return False


def refresh_async(lock=None) -> bool:
    """Runs the backtest in the background (first time: minutes — the history is downloaded). False if one
    is already running. `lock` (test mode's sandbox lock) is held only while the report is written."""
    if _running.is_set():
        return False
    _running.set()
    lock = lock or save_lock

    def work():
        try:
            report = run(save=False)
            if lock:  # while test mode's sandbox holds the lock, STATS_FILE points into its temporary folder
                with lock:
                    _save(report)
            else:
                _save(report)
        except Exception as e:  # noqa: BLE001 — no data now: the watch tries again later
            print(f"[Trading] backtest: {type(e).__name__}: {e}")
        finally:
            _running.clear()

    threading.Thread(target=work, daemon=True, name="backtest").start()
    return True


if __name__ == "__main__":
    from . import texts
    print(texts.strategy_table(run()))
