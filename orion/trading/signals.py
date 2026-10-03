"""
The three strategies and the signals they give — evaluated on CLOSED 1h candles. The same code serves
live forecasts, the backtest, the practice account and the lab, so what is measured is what is used.

  pullback  — 4h trend up and the daily trend not against; the 1h price dips to the fast EMA and closes
              back above it.
  breakout  — a 1h close above the highest high of the last `channel` candles, on high volume, ADX rising.
  reversal  — funding in its top 5 % of 90 days and the 4h RSI above 75: the crowd is long -> short.
Each one is mirrored for the other side. The stop sits beyond the last swing or 1.5 ATR, whichever is
further (at most 3 ATR); the target is `reward` × the stop distance.
"""
import json
import math
import time
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass, field
from statistics import pstdev

from . import MEMORY
from . import indicators as ind
from .data import HOUR, Bars

PARAMS_FILE = MEMORY / "trading_params.json"
STRATEGIES = ("pullback", "breakout", "reversal")
LABELS = {"pullback": "отскок в тренда", "breakout": "пробив", "reversal": "обрат при крайност"}
DEFAULTS = {
    "pullback": {"fast": 21, "slow": 55, "stop_atr": 1.5, "reward": 2.0},
    "breakout": {"channel": 20, "volume": 1.5, "stop_atr": 1.5, "reward": 2.0},
    "reversal": {"funding_pct": 0.95, "rsi": 75, "stop_atr": 1.5, "reward": 2.0},
}
TIME_STOP_HOURS = 48
FUNDING_DAYS = 90
WARMUP = 60                # 1h candles before the first signal
DAY = 24 * HOUR


@dataclass
class Signal:
    coin: str
    strategy: str
    side: str              # "long" | "short"
    time: int              # close time of the 1h candle that gave it (ms)
    entry: float
    stop: float
    target: float
    strength: int          # 1–5
    reasons: list[str] = field(default_factory=list)

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, saved: dict) -> "Signal":
        return cls(**{name: saved[name] for name in cls.__dataclass_fields__ if name in saved})


# --- Parameters ----------------------------------------------------------------------------------
def load_params() -> dict:
    """The current numbers of every strategy: the defaults + what the lab promoted."""
    try:
        saved = json.loads(PARAMS_FILE.read_text(encoding="utf-8")).get("current", {})
    except (OSError, ValueError):
        saved = {}
    return {name: {**DEFAULTS[name], **saved.get(name, {})} for name in STRATEGIES}


def save_params(strategy: str, numbers: dict, why: str) -> None:
    """The lab promotes new numbers for one strategy; the previous ones stay in the history (rollback)."""
    try:
        saved = json.loads(PARAMS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    current = saved.setdefault("current", {})
    saved.setdefault("history", []).append({"time": int(time.time() * 1000), "strategy": strategy,
                                            "old": current.get(strategy, DEFAULTS[strategy]), "new": numbers,
                                            "why": why})
    current[strategy] = numbers
    PARAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PARAMS_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")


# --- One coin, prepared ----------------------------------------------------------------------------
@dataclass
class Prepared:
    """A coin's candles with every indicator computed once — signals_at(i) only looks values up."""
    coin: str
    h1: Bars
    h4: Bars
    d1: Bars
    params: dict
    funding_t: list[int]
    funding_v: list[float]
    s: dict                          # indicator series by name
    i4: list[int]                    # per 1h candle: the last 4h candle closed by then (-1: none)
    i1d: list[int]                   # the same for daily candles
    btc_trend: list[int] | None      # BTC's 4h trend per 1h candle (ETH and SOL only)
    fear_greed: list[int | None]     # per 1h candle
    btc_h4: Bars | None = None       # kept to prepare again with other numbers (the lab)
    fear_greed_raw: list = field(default_factory=list)


def _closed_index(h1: Bars, other: Bars) -> list[int]:
    """For each 1h candle: the last candle of `other` that had closed when the 1h candle closed."""
    out, j = [], -1
    for i in range(len(h1)):
        end = h1.end(i)
        while j + 1 < len(other) and other.end(j + 1) <= end:
            j += 1
        out.append(j)
    return out


def _trend(fast: list, slow: list, close: list[float], j: int) -> int:
    if j < 0 or fast[j] is None or slow[j] is None:
        return 0
    if fast[j] > slow[j] and close[j] > slow[j]:
        return 1
    if fast[j] < slow[j] and close[j] < slow[j]:
        return -1
    return 0


def prepare(coin: str, h1: Bars, h4: Bars, d1: Bars, funding: list[tuple[int, float]], params: dict | None = None,
            btc_h4: Bars | None = None, fear_greed: list[tuple[int, int]] | None = None) -> Prepared:
    params = params or load_params()
    pullback, breakout = params["pullback"], params["breakout"]
    volume_avg = ind.sma(h1.v, 20)
    s = {
        "fast1": ind.ema(h1.c, int(pullback["fast"])), "slow1": ind.ema(h1.c, int(pullback["slow"])),
        "fast4": ind.ema(h4.c, int(pullback["fast"])), "slow4": ind.ema(h4.c, int(pullback["slow"])),
        "ema50d": ind.ema(d1.c, 50), "ema200d": ind.ema(d1.c, 200), "rsi4": ind.rsi(h4.c, 14),
        "atr1": ind.atr(h1.h, h1.l, h1.c, 14), "adx1": ind.adx(h1.h, h1.l, h1.c, 14),
        "vol1": [None] + volume_avg[:-1],          # the average of the 20 candles BEFORE each one
        "hi1": ind.channel_high(h1.h, int(breakout["channel"])),
        "lo1": ind.channel_low(h1.l, int(breakout["channel"])),
    }
    btc_trend = None
    if btc_h4 is not None:
        fast, slow = ind.ema(btc_h4.c, int(pullback["fast"])), ind.ema(btc_h4.c, int(pullback["slow"]))
        btc_trend = [_trend(fast, slow, btc_h4.c, j) for j in _closed_index(h1, btc_h4)]
    raw = list(fear_greed or [])
    days = [t for t, _ in raw]
    mood: list[int | None] = []
    for t in h1.t:
        k = bisect_right(days, t) - 1
        mood.append(raw[k][1] if k >= 0 and t - raw[k][0] < 2 * DAY else None)
    return Prepared(coin, h1, h4, d1, params, [t for t, _ in funding], [v for _, v in funding], s,
                    _closed_index(h1, h4), _closed_index(h1, d1), btc_trend, mood, btc_h4, raw)


def with_params(p: Prepared, params: dict) -> Prepared:
    """The same candles with other strategy numbers (the lab)."""
    return prepare(p.coin, p.h1, p.h4, p.d1, list(zip(p.funding_t, p.funding_v)), params, p.btc_h4,
                   p.fear_greed_raw)


# --- The rules -----------------------------------------------------------------------------------
def _trend4(p: Prepared, i: int) -> int:
    return _trend(p.s["fast4"], p.s["slow4"], p.h4.c, p.i4[i])


def _trend1d(p: Prepared, i: int) -> int:
    k = p.i1d[i]
    if k < 0:
        return 0
    e50, e200, close = p.s["ema50d"][k], p.s["ema200d"][k], p.d1.c[k]
    if e50 is None or e200 is None:
        return 0
    if close > e200 and e50 > e200:
        return 1
    if close < e200 and e50 < e200:
        return -1
    return 0


def funding_rank(p: Prepared, t: int) -> float | None:
    """Where the latest funding stands among the last 90 days: 0 — the lowest, 1 — the highest."""
    hi = bisect_right(p.funding_t, t)
    lo = bisect_left(p.funding_t, t - FUNDING_DAYS * DAY)
    window = p.funding_v[lo:hi]
    if len(window) < 30 * 24:  # less than a month of history — no opinion
        return None
    current = window[-1]
    return sum(1 for v in window if v <= current) / len(window)


def _pullback(p: Prepared, i: int, side: str) -> bool:
    sign = 1 if side == "long" else -1
    if _trend4(p, i) != sign or _trend1d(p, i) == -sign:
        return False
    fast, slow, c, h, l = p.s["fast1"], p.s["slow1"], p.h1.c, p.h1.h, p.h1.l  # noqa: E741
    window = range(i - 3, i + 1)
    if any(fast[x] is None or slow[x] is None for x in window):
        return False
    if side == "long":
        touched = any(l[x] <= fast[x] for x in window)
        held = all(c[x] > slow[x] for x in window)
        return touched and held and c[i] > fast[i] and c[i - 1] <= fast[i - 1]
    touched = any(h[x] >= fast[x] for x in window)
    held = all(c[x] < slow[x] for x in window)
    return touched and held and c[i] < fast[i] and c[i - 1] >= fast[i - 1]


def _breakout(p: Prepared, i: int, side: str, numbers: dict) -> bool:
    hi, lo, volume, adx = p.s["hi1"], p.s["lo1"], p.s["vol1"], p.s["adx1"]
    c, v = p.h1.c, p.h1.v
    if None in (hi[i], hi[i - 1], lo[i], lo[i - 1], volume[i], adx[i], adx[i - 1]):
        return False
    if v[i] < numbers["volume"] * volume[i] or adx[i] <= adx[i - 1]:
        return False
    trend = _trend4(p, i)
    if side == "long":
        return c[i] > hi[i] and c[i - 1] <= hi[i - 1] and trend >= 0
    return c[i] < lo[i] and c[i - 1] >= lo[i - 1] and trend <= 0


def _reversal(p: Prepared, i: int, side: str, numbers: dict) -> bool:
    j = p.i4[i]
    strength = p.s["rsi4"][j] if j >= 0 else None
    if strength is None:
        return False
    c, h, l = p.h1.c, p.h1.h, p.h1.l  # noqa: E741
    if side == "short":
        if strength <= numbers["rsi"] or c[i] >= l[i - 1]:
            return False
        rank = funding_rank(p, p.h1.end(i))
        return rank is not None and rank >= numbers["funding_pct"]
    if strength >= 100 - numbers["rsi"] or c[i] <= h[i - 1]:
        return False
    rank = funding_rank(p, p.h1.end(i))
    return rank is not None and rank <= 1 - numbers["funding_pct"]


def _levels(p: Prepared, i: int, side: str, numbers: dict) -> tuple[float, float] | None:
    entry, atr = p.h1.c[i], p.s["atr1"][i]
    if not atr:
        return None
    long = side == "long"
    swing = ind.last_pivot_low(p.h1.l, i) if long else ind.last_pivot_high(p.h1.h, i)
    distance = numbers["stop_atr"] * atr
    if swing is not None:
        distance = max(distance, (entry - swing if long else swing - entry) + 0.1 * atr)
    distance = min(distance, 3 * atr)
    sign = 1 if long else -1
    return entry - sign * distance, entry + sign * numbers["reward"] * distance


def _strength(p: Prepared, i: int, side: str) -> tuple[int, list[str]]:
    up = side == "long"
    sign = 1 if up else -1
    word = "нагоре" if up else "надолу"
    points, reasons = 1, []
    if _trend4(p, i) == sign and _trend1d(p, i) == sign:
        points += 1
        reasons.append(f"4-часовият и дневният тренд са {word}")
    volume = p.s["vol1"][i]
    if volume and p.h1.v[i] > volume:
        points += 1
        reasons.append("обемът е над средния")
    rank = funding_rank(p, p.h1.end(i))
    if rank is not None and (rank < 0.8 if up else rank > 0.2):
        points += 1
        reasons.append("финансирането не е претоварено срещу сделката")
    if p.btc_trend is not None:
        if p.btc_trend[i] == sign:
            points += 1
            reasons.append(f"биткойнът също върви {word}")
    else:
        mood = p.fear_greed[i]
        if mood is not None and (mood <= 80 if up else mood >= 20):
            points += 1
            reasons.append(f"страх/алчност {mood} — не е крайност срещу сделката")
    return points, reasons


def signals_at(p: Prepared, i: int, only: str | None = None) -> list[Signal]:
    """The signals that the closed 1h candle i gives (all strategies, or only one)."""
    if i < WARMUP or i >= len(p.h1):
        return []
    found = []
    for name in ((only,) if only else STRATEGIES):
        numbers = p.params[name]
        for side in ("long", "short"):
            if name == "pullback":
                fired = _pullback(p, i, side)
            elif name == "breakout":
                fired = _breakout(p, i, side, numbers)
            else:
                fired = _reversal(p, i, side, numbers)
            if not fired:
                continue
            levels = _levels(p, i, side, numbers)
            if not levels:
                continue
            strength, reasons = _strength(p, i, side)
            found.append(Signal(p.coin, name, side, p.h1.end(i), p.h1.c[i], levels[0], levels[1], strength,
                                [LABELS[name]] + reasons))
    return found


def latest(p: Prepared) -> list[Signal]:
    """The signals of the last closed candle."""
    return signals_at(p, len(p.h1) - 1)


# --- Context for „no signal“ ------------------------------------------------------------------------
@dataclass
class Context:
    price: float
    trend4: int
    trend1d: int
    support: float | None
    resistance: float | None
    low24: float
    high24: float
    funding_rank: float | None
    atr: float | None
    time: int


def range_24h(h1: Bars, i: int, days: int = 30) -> tuple[float, float]:
    """Where the price will likely be in 24 h (≈68 %): ± one standard deviation of daily moves."""
    start = max(1, i - days * 24 + 1)
    returns = [math.log(h1.c[k] / h1.c[k - 1]) for k in range(start, i + 1) if h1.c[k - 1] > 0]
    sigma = pstdev(returns) * math.sqrt(24) if len(returns) > 24 else 0.0
    price = h1.c[i]
    return price * math.exp(-sigma), price * math.exp(sigma)


def context(p: Prepared, i: int | None = None) -> Context:
    i = len(p.h1) - 1 if i is None else i
    price = p.h1.c[i]
    support, resistance = ind.levels(p.h1.h, p.h1.l, i, price)
    low, high = range_24h(p.h1, i)
    return Context(price, _trend4(p, i), _trend1d(p, i), support, resistance, low, high,
                   funding_rank(p, p.h1.end(i)), p.s["atr1"][i], p.h1.end(i))
