"""
Market data for the trading package: candles, funding, coin details.

Live signals use Hyperliquid (where sir trades). The backtest needs years, but Hyperliquid's API returns
only the latest 5000 candles (≈7 months of 1h), so the history comes from Binance's public spot klines
(no key) from 2023-05-12 — when Hyperliquid's funding history starts. History and funding are cached in
memory/trading_cache/ and only the missing tail is downloaded.
"""
import json
import time
import urllib.error
import urllib.request
from bisect import bisect_left
from dataclasses import dataclass, field

from . import CACHE_DIR, COINS, MEMORY

HL_INFO = "https://api.hyperliquid.xyz/info"
BINANCE = "https://data-api.binance.vision/api/v3/klines"
FEAR_GREED = "https://api.alternative.me/fng/?limit=0"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Orion"
HOUR = 3_600_000
INTERVALS = {"1m": 60_000, "1h": HOUR, "4h": 4 * HOUR, "1d": 24 * HOUR}
HISTORY_START = 1683849600000   # 2023-05-12 00:00 UTC
DEFAULT_FUNDING = 0.0000125     # Hyperliquid's hourly baseline (0.01 % per 8 h) before its history starts
PAGE_PAUSE = 2.5                # between funding pages after the 10th — Hyperliquid's rate limit
OI_FILE = MEMORY / "trading_oi.json"
OI_LIMIT = 10_000


@dataclass
class Bars:
    """Candles of one interval: open time (ms, UTC) and OHLCV, oldest first."""
    interval: int
    t: list[int] = field(default_factory=list)
    o: list[float] = field(default_factory=list)
    h: list[float] = field(default_factory=list)
    l: list[float] = field(default_factory=list)  # noqa: E741
    c: list[float] = field(default_factory=list)
    v: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.t)

    def add(self, t: int, o: float, h: float, l: float, c: float, v: float) -> None:  # noqa: E741
        self.t.append(t)
        self.o.append(o)
        self.h.append(h)
        self.l.append(l)
        self.c.append(c)
        self.v.append(v)

    def end(self, i: int) -> int:
        """When candle i closes (ms)."""
        return self.t[i] + self.interval

    def since(self, t_ms: int) -> "Bars":
        """The candles that open at or after t_ms."""
        k = bisect_left(self.t, t_ms)
        return Bars(self.interval, self.t[k:], self.o[k:], self.h[k:], self.l[k:], self.c[k:], self.v[k:])

    def to_json(self) -> dict:
        return {"interval": self.interval,
                "rows": [list(row) for row in zip(self.t, self.o, self.h, self.l, self.c, self.v)]}

    @classmethod
    def from_json(cls, saved: dict) -> "Bars":
        bars = cls(int(saved["interval"]))
        for row in saved["rows"]:
            bars.add(int(row[0]), *(float(x) for x in row[1:6]))
        return bars


def resample(bars: Bars, interval: int) -> Bars:
    """1h candles -> 4h or 1d candles aligned to UTC (00:00, 04:00…). Incomplete buckets are dropped."""
    out = Bars(interval)
    per = interval // bars.interval
    bucket: list[int] = []
    for i, t in enumerate(bars.t):
        if bucket and t // interval != bars.t[bucket[0]] // interval:
            _flush(bars, out, bucket, per, interval)
            bucket = []
        bucket.append(i)
    if bucket:
        _flush(bars, out, bucket, per, interval)
    return out


def _flush(src: Bars, dst: Bars, idx: list[int], per: int, interval: int) -> None:
    if len(idx) < per:  # a gap in the data or the unfinished last bucket
        return
    dst.add(src.t[idx[0]] // interval * interval, src.o[idx[0]], max(src.h[i] for i in idx),
            min(src.l[i] for i in idx), src.c[idx[-1]], sum(src.v[i] for i in idx))


# --- HTTP (tests replace these) --------------------------------------------------------------------
def _post(body: dict):
    """Hyperliquid's info API; waits and retries when it says „too many requests“."""
    payload = json.dumps(body).encode()
    for attempt in range(4):
        request = urllib.request.Request(HL_INFO, data=payload,
                                         headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def _get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _now() -> int:
    return int(time.time() * 1000)


# --- Hyperliquid (live) ----------------------------------------------------------------------------
def live_bars(coin: str, interval: str, count: int = 1000) -> Bars:
    """The latest closed Hyperliquid candles (the unfinished one is dropped)."""
    step = INTERVALS[interval]
    now = _now()
    rows = _post({"type": "candleSnapshot",
                  "req": {"coin": coin, "interval": interval, "startTime": now - step * (count + 1), "endTime": now}})
    bars = Bars(step)
    for row in rows:
        if int(row["t"]) + step <= now:
            bars.add(int(row["t"]), float(row["o"]), float(row["h"]), float(row["l"]), float(row["c"]),
                     float(row["v"]))
    return bars


@dataclass
class Asset:
    coin: str
    mid: float
    mark: float
    funding: float
    open_interest: float
    premium: float
    sz_decimals: int
    max_leverage: int


def assets() -> dict[str, Asset]:
    """Price, funding, open interest and order rules of BTC, ETH and SOL on Hyperliquid now."""
    meta, contexts = _post({"type": "metaAndAssetCtxs"})
    found = {}
    for info, ctx in zip(meta["universe"], contexts):
        if info["name"] in COINS:
            found[info["name"]] = Asset(
                info["name"], float(ctx.get("midPx") or ctx["markPx"]), float(ctx["markPx"]), float(ctx["funding"]),
                float(ctx["openInterest"]), float(ctx.get("premium") or 0), int(info["szDecimals"]),
                int(info["maxLeverage"]))
    return found


def record_open_interest(found: dict[str, Asset]) -> None:
    """Hyperliquid has no open-interest history: the watch keeps its own snapshots."""
    try:
        rows = json.loads(OI_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    rows.append({"time": _now(), **{coin: a.open_interest for coin, a in found.items()}})
    OI_FILE.parent.mkdir(parents=True, exist_ok=True)
    OI_FILE.write_text(json.dumps(rows[-OI_LIMIT:]), encoding="utf-8")


# --- Funding -----------------------------------------------------------------------------------
def _funding_pages(coin: str, start: int) -> list[tuple[int, float]]:
    rows, pages = [], 0
    while True:
        page = _post({"type": "fundingHistory", "coin": coin, "startTime": start})
        fresh = [(int(p["time"]), float(p["fundingRate"])) for p in page if int(p["time"]) >= start]
        rows.extend(fresh)
        pages += 1
        if len(page) < 500 or not fresh:
            return rows
        start = fresh[-1][0] + 1
        if pages >= 10:
            time.sleep(PAGE_PAUSE)


def funding(coin: str) -> list[tuple[int, float]]:
    """Hourly funding rates [(time ms, rate)] since HISTORY_START — cached, only the tail is fetched."""
    path = CACHE_DIR / f"{coin}_funding.json"
    try:
        rows = [(int(t), float(r)) for t, r in json.loads(path.read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        rows = []
    fresh = _funding_pages(coin, rows[-1][0] + 1 if rows else HISTORY_START)
    if fresh:
        rows.extend(fresh)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def recent_funding(coin: str, days: int = 90) -> list[tuple[int, float]]:
    """The last `days` of funding for a live forecast: the cache when it is fresh, else a direct short download
    (building the full cache takes minutes — the backtest does that in the background)."""
    path = CACHE_DIR / f"{coin}_funding.json"
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached and _now() - int(cached[-1][0]) < 3 * 24 * HOUR:
            return funding(coin)
    except (OSError, ValueError):
        pass
    return _funding_pages(coin, _now() - days * 24 * HOUR)


# --- Binance history -------------------------------------------------------------------------
def history(coin: str) -> Bars:
    """1h Binance candles from HISTORY_START until the last closed hour — cached."""
    path = CACHE_DIR / f"{coin}_1h.json"
    try:
        bars = Bars.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError):
        bars = Bars(HOUR)
    now = _now()
    start = bars.t[-1] + HOUR if bars.t else HISTORY_START
    added = False
    while start + HOUR <= now:
        rows = _get(f"{BINANCE}?symbol={coin}USDT&interval=1h&startTime={start}&limit=1000")
        if not rows:
            break
        for row in rows:
            t = int(row[0])
            if t + HOUR <= now and (not bars.t or t > bars.t[-1]):
                bars.add(t, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
                added = True
        if len(rows) < 1000:
            break
        start = int(rows[-1][0]) + HOUR
    if added:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(bars.to_json()), encoding="utf-8")
    return bars


def fear_greed() -> list[tuple[int, int]]:
    """Daily Fear & Greed values [(day start ms, value)], oldest first — cached for 6 hours."""
    path = CACHE_DIR / "fear_greed.json"
    try:
        if time.time() - path.stat().st_mtime < 6 * 3600:
            return [(int(t), int(v)) for t, v in json.loads(path.read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        pass
    rows = sorted((int(d["timestamp"]) * 1000, int(d["value"])) for d in _get(FEAR_GREED)["data"])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")
    return rows
