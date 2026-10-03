# Crypto Forecasts and Hyperliquid Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Orion gives honest, measured forecasts for BTC/ETH/SOL and opens/closes long and short positions on Hyperliquid — every real order only after sir presses „Одобри“ — and test mode practises trading on a virtual account.

**Architecture:** A new package `orion/trading/` with one purpose per file: data (Hyperliquid live + Binance history, cached), indicators, signals (three strategies, one code path for live/backtest/practice), backtest (70/30 honest split, costs), journal (live record), risk (hard limits, pure), settings (DPAPI-encrypted keys), exchange (the only file with a key; approval enforced inside), market (assembles a coin's data), texts (Bulgarian answers), watcher (background thread), practice + lab (test mode). Skills in `skills/crypto_trading_skills.py`; reflexes/router/brain wiring; React chip, key dialog and chart levels.

**Tech Stack:** Python 3.12, `hyperliquid-python-sdk` 0.24 (+ `eth-account`), urllib for public data, ctypes DPAPI, pytest; React 19 + Vite 8 + Vitest for the window.

**Spec:** `docs/superpowers/specs/2026-10-03-crypto-trading-design.md`

## Global Constraints

- Coins: only `BTC`, `ETH`, `SOL`; anything else → „засега търгувам само биткойн, етериум и солана“.
- Default limits (sir chose aggressive): `risk_pct 2.0`, `max_leverage 10`, `daily_loss_pct 6.0`, `max_positions 3`; isolated margin; liquidation distance ≥ 1.5 × stop distance; Hyperliquid minimum order $10.
- Every real open and close goes through `orion.confirm.ask` inside `orion/trading/exchange.py`. The only paths without approval: virtual practice trades (never touch the exchange) and `exchange.testnet_check()` (hard-wired testnet, minimum size).
- Default network `testnet`; mainnet only via `switch_trading_network` after a warning dialog. While test mode's `Sandbox` is active, `exchange.blocked = True` refuses every exchange call.
- A position never stays without a stop: missing stop → re-placed once → else closed at market immediately. Stops never move further away.
- The language model never computes a trading number and has no tool that changes limits; all numbers come from code.
- Keys: only an agent (API) private key + master address, typed in the key dialog (never the chat), stored DPAPI-encrypted in `trading_settings.json` (git-ignored). Seed phrases are refused. Text that looks like a key/seed typed in the chat is never processed or logged.
- Strategy enable rule (out-of-sample, last 30 %): ≥30 trades, average R > 0 after costs, profit factor ≥ 1.1.
- Costs: taker fee 0.045 % per side; slippage BTC 0.02 %, ETH 0.03 %, SOL 0.05 % per side; hourly funding (history from Hyperliquid; 0.00125 %/h before 2023-05-12). A candle touching stop and target counts as the stop.
- Horizon: closed 1h candles, 4h/1d filters, 48 h time stop.
- Watch: every 15 min; announce strength ≥ 4 + enabled strategy, same coin/side at most once per 6 h; voice only 08:00–23:00, journal always.
- Test mode: trading practice every round; the old skill/understanding checks every 3rd round.
- Spoken/answer texts in Bulgarian; window chips and labels in English (existing convention); code comments in English.
- Data files: `memory/trading_*.json` and `memory/trading_cache/` (memory/ is git-ignored); never commit personal data; never push.
- No automated test ever sends a real order or needs the network.

## Review Focus

1. A private key or seed phrase typed into the chat → it must never reach the model, the journal or `logs/orion.log`; Orion warns and opens the key dialog. (Test in Task 12.)
2. Testnet prices differ from mainnet by thousands of dollars → stop/target are re-anchored to the trading network's current price by the signal's distances, never sent as mainnet levels. (Test in Task 10.)
3. No internet / Hyperliquid down while sir asks for a forecast → a clear „няма данни“ answer, never old numbers presented as live. (Test in Task 10.)
4. Orion closed for days with practice trades open → they settle from the candles when it starts again, or expire if older than the candle window — never stuck open. (Test in Task 13.)
5. „Затвори всичко“ with no known open positions → not a trading command (it may mean windows). (Test in Task 11.)

## File Structure

| File | Responsibility |
|---|---|
| `orion/trading/__init__.py` | Coins, names, memory paths, coin parsing, `looks_secret`, key-dialog hook |
| `orion/trading/data.py` | `Bars`, resample, Hyperliquid live candles/assets/funding, Binance history, Fear & Greed, OI snapshots — cached |
| `orion/trading/indicators.py` | Pure indicator series (SMA, EMA, RSI, ATR, ADX, channels, pivots, levels) |
| `orion/trading/signals.py` | Parameters, `Signal`, `Prepared`, the three strategies, strength, context, 24 h range |
| `orion/trading/market.py` | Assembles a coin's `Prepared` from history (backtest/lab) or live (forecast/watch/practice) |
| `orion/trading/backtest.py` | `exit_walk`, costs, `simulate`, `Stats`, the 70/30 run, the report file, refresh |
| `orion/trading/journal.py` | Live record of signals and trades, outcome resolution, „колко позна“ |
| `orion/trading/risk.py` | `Limits`, `AccountState`, `OrderPlan`, `plan()` — every hard limit, price/size rounding |
| `orion/trading/settings.py` | `trading_settings.json`, DPAPI encryption, key validation |
| `orion/trading/exchange.py` | Hyperliquid SDK client; `place`/`close`/`move_stop_to_entry` with approval; protection check; `testnet_check` |
| `orion/trading/texts.py` | Every Bulgarian sentence about forecasts, strategies, record, account, fills |
| `orion/trading/watcher.py` | Background watch thread: signals, positions chip, fills, time stop, resolve, stale backtest |
| `orion/trading/practice.py` | Virtual $10 000 account and the test-mode trading stage |
| `orion/trading/lab.py` | Parameter variants and the two promotion gates |
| `skills/crypto_trading_skills.py` | The 13 skills the model calls |
| `orion/reflexes.py`, `orion/router.py`, `orion/brain.py`, `config.py` | Commands without the model, skill group words, intent nudge, persona line |
| `orion/self_test.py`, `orion/self_test_cases.py` | Trading stage every round, sandbox block, report; new asks and cases |
| `app.py` | Watcher thread, key-dialog hook, chart for forecasts, `save_trading_key`, secret guard |
| `web/src/{store.js,bridge.js,util.js}`, `components/{Jobs,KeyDialog,Stage,Journal}.jsx`, `engine/chart.js`, `styles.css` | Trading chip, key dialog, entry/stop/target lines |
| `tests/test_trading_*.py`, `web/src/components/*.test.jsx` | Tests |

Run Python tests from the project root: `python -m pytest -q`. Web tests: `cd web && npm test`. Build the window: `cd web && npm run build`.

---
### Task 1: The trading package, coin names, the secret guard and the SDK

**Files:**
- Create: `orion/trading/__init__.py`
- Modify: `requirements.txt` (append one line)
- Test: `tests/test_trading_coins.py`

**Interfaces:**
- Consumes: `config.BASE_DIR`
- Produces: `COINS: tuple[str, ...] = ("BTC", "ETH", "SOL")`, `NAMES: dict[str, str]`, `MEMORY: Path`, `CACHE_DIR: Path`, `ONLY_THREE: str`, `coins_in(text: str) -> list[str]`, `coin_from_text(text: str) -> str` (raises `ValueError(ONLY_THREE)`), `looks_secret(text: str) -> bool`, `show_key_dialog: Callable[[str], None]` (app.py replaces it; argument is `"testnet"` or `"mainnet"`).

- [ ] **Step 1: Check free space on C: and install the SDK**

Run (PowerShell): `Get-PSDrive C | Select-Object Free`
Expected: more than 1 GB free (it was 7.7 GB on 2026-10-03). If less, stop and tell sir.

Run: `python -m pip install "hyperliquid-python-sdk>=0.24"`
Expected: `Successfully installed ... hyperliquid-python-sdk-0.24.0 ... eth-account-...`

Append to `requirements.txt`:

```
hyperliquid-python-sdk>=0.24  # търговия в Hyperliquid: поръчки с API ключ, който НЕ може да тегли
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_trading_coins.py`:

```python
import pytest

from orion import trading


@pytest.mark.parametrize("text, coin", [
    ("биткойна", "BTC"), ("Какво ще прави биткойнът?", "BTC"), ("BTC", "BTC"), ("bitcoin", "BTC"),
    ("биткоин", "BTC"), ("етериума", "ETH"), ("етер", "ETH"), ("етерът", "ETH"), ("ETH", "ETH"),
    ("Ethereum", "ETH"), ("соланата", "SOL"), ("солана", "SOL"), ("SOL", "SOL"),
])
def test_coin_from_text(text, coin):
    assert trading.coin_from_text(text) == coin


def test_other_coins_are_refused():
    with pytest.raises(ValueError, match="само биткойн"):
        trading.coin_from_text("доги")


def test_coins_in_lists_every_coin_named():
    assert trading.coins_in("сравни биткойн и солана") == ["BTC", "SOL"]


def test_salt_and_ether_words_are_not_coins():
    assert trading.coins_in("сол и пипер") == []
    assert trading.coins_in("етерична мазнина") == []


@pytest.mark.parametrize("text", [
    "0x" + "ab" * 32,
    "ключът ми е " + "1f" * 32,
    " ".join(["abandon"] * 11 + ["about"]),
    " ".join(["zoo"] * 24),
])
def test_secrets_are_recognised(text):
    assert trading.looks_secret(text)


@pytest.mark.parametrize("text", [
    "Отвори лонг на биткойн", "0xAbC123", "what is the price of bitcoin today my friend",
    "Какво ще прави етериумът днес?",
])
def test_normal_text_is_not_a_secret(text):
    assert not trading.looks_secret(text)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_coins.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'orion.trading'`

- [ ] **Step 4: Write the implementation**

Create `orion/trading/__init__.py`:

```python
"""
Crypto forecasts and trading on Hyperliquid — Bitcoin, Ethereum and Solana.

Design: docs/superpowers/specs/2026-10-03-crypto-trading-design.md. Every number (signals, backtest,
risk) is computed in code; the language model only explains it. Every real order needs sir's „Одобри“,
enforced in orion/trading/exchange.py.
"""
import re
from typing import Callable

import config

COINS = ("BTC", "ETH", "SOL")
NAMES = {"BTC": "Биткойн", "ETH": "Етериум", "SOL": "Солана"}
MEMORY = config.BASE_DIR / "memory"
CACHE_DIR = MEMORY / "trading_cache"
ONLY_THREE = "засега търгувам само биткойн, етериум и солана"

_COIN_RES = {
    "BTC": re.compile(r"биткойн|биткоин|bitcoin|\bbtc\b", re.IGNORECASE),
    "ETH": re.compile(r"етериум|ефириум|\bетер(?:а|ът)?\b|ethereum|\beth\b", re.IGNORECASE),
    "SOL": re.compile(r"солан|solana|\bsol\b", re.IGNORECASE),
}
_HEX64 = re.compile(r"(?:0x)?[0-9a-fA-F]{64}")
_SEED_LENGTHS = {12, 15, 18, 21, 24}

# app.py replaces it: shows the key dialog in the window ("testnet" or "mainnet").
show_key_dialog: Callable[[str], None] = lambda network: None


def coins_in(text: str) -> list[str]:
    """The coins named in the text, in the order BTC, ETH, SOL."""
    return [coin for coin, pattern in _COIN_RES.items() if pattern.search(text or "")]


def coin_from_text(text: str) -> str:
    """'BTC' for „биткойна“, „BTC“, „Bitcoin“…; ValueError for any other coin."""
    found = coins_in(text)
    if not found:
        raise ValueError(ONLY_THREE)
    return found[0]


def looks_secret(text: str) -> bool:
    """A private key (64 hex characters) or a recovery phrase (12–24 lowercase Latin words) —
    such text is never processed, logged or sent to the model."""
    text = text or ""
    if _HEX64.search(text):
        return True
    tokens = text.split()
    return len(tokens) in _SEED_LENGTHS and all(re.fullmatch(r"[a-z]+", token) for token in tokens)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_coins.py -q`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add orion/trading/__init__.py tests/test_trading_coins.py requirements.txt
git commit -m "Trading: package, coin names, secret guard, Hyperliquid SDK"
```

---

### Task 2: Market data — candles, history, funding, coin details

**Files:**
- Create: `orion/trading/data.py`
- Test: `tests/test_trading_data.py`

**Interfaces:**
- Consumes: `orion.trading.COINS`, `CACHE_DIR`, `MEMORY`
- Produces:
  - `HOUR = 3_600_000`, `INTERVALS: dict[str, int]`, `HISTORY_START = 1683849600000`, `DEFAULT_FUNDING = 0.0000125`
  - `@dataclass Bars(interval: int, t, o, h, l, c, v: lists)` with `__len__`, `add(t, o, h, l, c, v)`, `end(i) -> int`, `since(t_ms) -> Bars`, `to_json() -> dict`, `Bars.from_json(dict) -> Bars`
  - `resample(bars: Bars, interval: int) -> Bars`
  - `live_bars(coin: str, interval: str, count: int = 1000) -> Bars` (Hyperliquid, closed candles only)
  - `history(coin: str) -> Bars` (Binance 1h since `HISTORY_START`, cached)
  - `funding(coin: str) -> list[tuple[int, float]]` (full, cached), `recent_funding(coin: str, days: int = 90) -> list[tuple[int, float]]`
  - `@dataclass Asset(coin, mid, mark, funding, open_interest, premium, sz_decimals, max_leverage)`; `assets() -> dict[str, Asset]`
  - `fear_greed() -> list[tuple[int, int]]`; `record_open_interest(found: dict[str, Asset]) -> None` (writes `OI_FILE`)
  - Module seams for tests: `_post(body) -> Any`, `_get(url) -> Any`, `_now() -> int`, `PAGE_PAUSE: float`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_data.py`:

```python
import json
import re

import pytest

from orion.trading import data
from orion.trading.data import HOUR, Bars


def hourly(n, start=0, close=100.0):
    bars = Bars(HOUR)
    for k in range(n):
        bars.add(start + k * HOUR, close + k, close + k + 2, close + k - 1, close + k + 1, 10.0)
    return bars


def test_resample_builds_aligned_4h_candles_and_drops_the_unfinished_one():
    bars = hourly(10)                                   # 00:00 … 09:00 -> 4h at 00:00 and 04:00; 08:00 unfinished
    four = data.resample(bars, 4 * HOUR)
    assert four.t == [0, 4 * HOUR]
    assert four.o == [100.0, 104.0]
    assert four.h == [105.0, 109.0]
    assert four.l == [99.0, 103.0]
    assert four.c == [104.0, 108.0]
    assert four.v == [40.0, 40.0]


def test_bars_json_round_trip_and_since():
    bars = hourly(5)
    again = Bars.from_json(json.loads(json.dumps(bars.to_json())))
    assert again.t == bars.t and again.c == bars.c and again.interval == HOUR
    assert again.since(3 * HOUR).t == [3 * HOUR, 4 * HOUR]
    assert bars.end(0) == HOUR


def test_live_bars_drop_the_candle_that_is_still_open(monkeypatch):
    now = 10 * HOUR + 1800_000
    rows = [{"t": k * HOUR, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "3"} for k in range(11)]
    monkeypatch.setattr(data, "_now", lambda: now)
    monkeypatch.setattr(data, "_post", lambda body: rows)
    bars = data.live_bars("BTC", "1h", 20)
    assert len(bars) == 10 and bars.t[-1] == 9 * HOUR and bars.c[0] == 1.5


def fake_binance(calls, clock):
    def get(url):
        start = int(re.search(r"startTime=(\d+)", url)[1])
        calls.append(start)
        rows, t = [], start
        while t <= clock() and len(rows) < 1000:       # Binance also returns the unfinished hour
            rows.append([t, "1", "2", "0.5", "1.5", "10"])
            t += HOUR
        return rows
    return get


def test_history_downloads_once_then_only_the_tail(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path)
    now = data.HISTORY_START + 2500 * HOUR + 1800_000
    calls = []
    monkeypatch.setattr(data, "_now", lambda: now)
    monkeypatch.setattr(data, "_get", fake_binance(calls, lambda: now))
    bars = data.history("SOL")
    assert len(bars) == 2500 and bars.t[0] == data.HISTORY_START
    assert calls == [data.HISTORY_START, data.HISTORY_START + 1000 * HOUR, data.HISTORY_START + 2000 * HOUR]
    calls.clear()
    now += 3 * HOUR
    again = data.history("SOL")
    assert len(again) == 2503
    assert calls == [data.HISTORY_START + 2500 * HOUR]


def test_funding_pages_and_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(data, "PAGE_PAUSE", 0)
    pages = []

    def post(body):
        pages.append(body["startTime"])
        start = body["startTime"]
        count = 500 if len(pages) == 1 else 10
        return [{"coin": "BTC", "fundingRate": "0.0001", "premium": "0", "time": start + k * HOUR}
                for k in range(count)]

    monkeypatch.setattr(data, "_post", post)
    rows = data.funding("BTC")
    assert len(rows) == 510 and rows[0] == (data.HISTORY_START, 0.0001)
    assert pages == [data.HISTORY_START, data.HISTORY_START + 499 * HOUR + 1]
    assert (tmp_path / "BTC_funding.json").exists()


def test_assets_reads_the_three_coins(monkeypatch):
    meta = {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
                         {"name": "DOGE", "szDecimals": 0, "maxLeverage": 10},
                         {"name": "SOL", "szDecimals": 2, "maxLeverage": 20}]}
    ctx = [{"funding": "0.00001", "openInterest": "100", "premium": "-0.0003", "markPx": "84465.0", "midPx": "84468.5"},
           {"funding": "0", "openInterest": "1", "premium": "0", "markPx": "0.1", "midPx": "0.1"},
           {"funding": "0.00002", "openInterest": "5", "premium": "0", "markPx": "118.4", "midPx": None}]
    monkeypatch.setattr(data, "_post", lambda body: [meta, ctx])
    found = data.assets()
    assert set(found) == {"BTC", "SOL"}
    assert found["BTC"].mid == 84468.5 and found["BTC"].sz_decimals == 5 and found["BTC"].max_leverage == 40
    assert found["SOL"].mid == 118.4                     # no mid -> the mark price


def test_open_interest_snapshots_are_appended_and_capped(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "OI_FILE", tmp_path / "oi.json")
    monkeypatch.setattr(data, "OI_LIMIT", 2)
    monkeypatch.setattr(data, "_now", lambda: 5)
    asset = data.Asset("BTC", 1, 1, 0, 123.0, 0, 5, 40)
    for _ in range(3):
        data.record_open_interest({"BTC": asset})
    rows = json.loads((tmp_path / "oi.json").read_text(encoding="utf-8"))
    assert rows == [{"time": 5, "BTC": 123.0}, {"time": 5, "BTC": 123.0}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_data.py -q`
Expected: FAIL — `ImportError: cannot import name 'data' from 'orion.trading'`

- [ ] **Step 3: Write the implementation**

Create `orion/trading/data.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_data.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orion/trading/data.py tests/test_trading_data.py
git commit -m "Trading data: Hyperliquid live candles, Binance history, funding, coin details (cached)"
```

---

### Task 3: Indicator series

**Files:**
- Create: `orion/trading/indicators.py`
- Test: `tests/test_trading_indicators.py`

**Interfaces:**
- Consumes: nothing
- Produces (all return a list as long as the input, `None` while warming up): `sma(values, n)`, `ema(values, n)`, `rsi(values, n=14)`, `atr(h, l, c, n=14)`, `adx(h, l, c, n=14)`, `channel_high(h, n)`, `channel_low(l, n)` (extreme of the n candles BEFORE i), `last_pivot_low(l, i, width=3, lookback=48) -> float | None`, `last_pivot_high(h, i, width=3, lookback=48) -> float | None`, `levels(h, l, i, price, width=5, lookback=240) -> tuple[float | None, float | None]` (support below, resistance above).

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_indicators.py`:

```python
import pytest

from orion.trading import indicators as ind


def test_sma():
    assert ind.sma([1, 2, 3, 4, 5], 2) == [None, 1.5, 2.5, 3.5, 4.5]


def test_ema_is_seeded_with_the_simple_average():
    out = ind.ema([1.0, 2.0, 3.0, 4.0], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)              # 4 * 0.5 + 2 * 0.5
    assert ind.ema([5.0] * 30, 10)[-1] == pytest.approx(5.0)


def test_rsi_extremes_and_balance():
    assert ind.rsi([float(x) for x in range(30)])[-1] == pytest.approx(100.0)
    assert ind.rsi([float(30 - x) for x in range(30)])[-1] == pytest.approx(0.0)
    zigzag = [100.0 + (1 if k % 2 else 0) for k in range(60)]
    assert ind.rsi(zigzag)[-1] == pytest.approx(50.0, abs=3)
    assert ind.rsi([1.0] * 10)[-1] is None


def test_atr_of_constant_range():
    n = 40
    out = ind.atr([12.0] * n, [10.0] * n, [11.0] * n, 14)
    assert out[12] is None and out[13] == pytest.approx(2.0) and out[-1] == pytest.approx(2.0)


def test_adx_is_high_in_a_trend_and_low_in_chop():
    n = 80
    up = ind.adx([k + 1.0 for k in range(n)], [float(k) for k in range(n)], [k + 0.5 for k in range(n)])
    assert up[-1] > 50
    h = [11.0 if k % 2 == 0 else 10.0 for k in range(n)]
    l = [10.0 if k % 2 == 0 else 9.0 for k in range(n)]
    chop = ind.adx(h, l, [(a + b) / 2 for a, b in zip(h, l)])
    assert chop[-1] < 20
    assert up[26] is None and up[27] is not None


def test_channels_exclude_the_current_candle():
    assert ind.channel_high([1.0, 5.0, 2.0, 3.0, 9.0], 2) == [None, None, 5.0, 5.0, 3.0]
    assert ind.channel_low([5.0, 1.0, 4.0, 3.0, 0.0], 2) == [None, None, 1.0, 1.0, 3.0]


def test_pivots_need_confirmation():
    lows = [5.0, 4.0, 3.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert ind.last_pivot_low(lows, 8, width=2) == 2.0
    assert ind.last_pivot_low(lows, 4, width=2) is None   # the low at 3 is not confirmed yet
    highs = [1.0, 2.0, 3.0, 9.0, 3.0, 2.0, 1.0, 1.5]
    assert ind.last_pivot_high(highs, 7, width=2) == 9.0


def test_levels_pick_the_nearest_support_and_resistance():
    h = [10, 12, 10, 9, 10, 15, 10, 9, 10, 11, 10, 10, 10, 10, 10]
    l = [8, 9, 8, 5, 8, 9, 8, 7, 8, 9, 8, 8, 8, 8, 8]
    support, resistance = ind.levels([float(x) for x in h], [float(x) for x in l], 14, 10.5, width=1)
    assert support == 8.0 and resistance == 11.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_indicators.py -q`
Expected: FAIL — `ImportError: cannot import name 'indicators'`

- [ ] **Step 3: Write the implementation**

Create `orion/trading/indicators.py`:

```python
"""Indicator series for the trading strategies — pure functions, one value per candle (None while warming up)."""
from collections import deque

Series = list[float | None]


def sma(values: list[float], n: int) -> Series:
    out: Series = []
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= n:
            total -= values[i - n]
        out.append(total / n if i >= n - 1 else None)
    return out


def ema(values: list[float], n: int) -> Series:
    """Exponential average, seeded with the simple average of the first n values."""
    out: Series = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    value = sum(values[:n]) / n
    out[n - 1] = value
    for i in range(n, len(values)):
        value = values[i] * k + value * (1 - k)
        out[i] = value
    return out


def _rsi(gain: float, loss: float) -> float:
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100 - 100 / (1 + gain / loss)


def rsi(values: list[float], n: int = 14) -> Series:
    """Wilder's RSI."""
    out: Series = [None] * len(values)
    if len(values) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / n, losses / n
    out[n] = _rsi(avg_gain, avg_loss)
    for i in range(n + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(change, 0.0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-change, 0.0)) / n
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def true_range(h: list[float], l: list[float], c: list[float]) -> list[float]:  # noqa: E741
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]


def atr(h: list[float], l: list[float], c: list[float], n: int = 14) -> Series:  # noqa: E741
    """Wilder's average true range."""
    out: Series = [None] * len(c)
    if len(c) < n:
        return out
    tr = true_range(h, l, c)
    value = sum(tr[:n]) / n
    out[n - 1] = value
    for i in range(n, len(c)):
        value = (value * (n - 1) + tr[i]) / n
        out[i] = value
    return out


def adx(h: list[float], l: list[float], c: list[float], n: int = 14) -> Series:  # noqa: E741
    """Wilder's ADX — trend strength 0–100 (above ~25: a trend). First value at candle 2n − 1."""
    size = len(c)
    out: Series = [None] * size
    if size < 2 * n + 1:
        return out
    tr = true_range(h, l, c)
    plus = [0.0] + [max(h[i] - h[i - 1], 0.0) if h[i] - h[i - 1] > l[i - 1] - l[i] else 0.0 for i in range(1, size)]
    minus = [0.0] + [max(l[i - 1] - l[i], 0.0) if l[i - 1] - l[i] > h[i] - h[i - 1] else 0.0 for i in range(1, size)]
    tr_s, plus_s, minus_s = sum(tr[1:n + 1]), sum(plus[1:n + 1]), sum(minus[1:n + 1])
    dx = []
    for i in range(n, size):
        if i > n:
            tr_s = tr_s - tr_s / n + tr[i]
            plus_s = plus_s - plus_s / n + plus[i]
            minus_s = minus_s - minus_s / n + minus[i]
        pdi = 100 * plus_s / tr_s if tr_s else 0.0
        mdi = 100 * minus_s / tr_s if tr_s else 0.0
        dx.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
    value = sum(dx[:n]) / n
    out[2 * n - 1] = value
    for k in range(n, len(dx)):
        value = (value * (n - 1) + dx[k]) / n
        out[n + k] = value
    return out


def channel_high(h: list[float], n: int) -> Series:
    """The highest high of the n candles BEFORE each candle (Donchian without the current one)."""
    out: Series = [None] * len(h)
    window: deque[int] = deque()
    for i, value in enumerate(h):
        while window and window[0] < i - n:
            window.popleft()
        if i >= n:
            out[i] = h[window[0]]
        while window and h[window[-1]] <= value:
            window.pop()
        window.append(i)
    return out


def channel_low(l: list[float], n: int) -> Series:  # noqa: E741
    """The lowest low of the n candles BEFORE each candle."""
    out: Series = [None] * len(l)
    window: deque[int] = deque()
    for i, value in enumerate(l):
        while window and window[0] < i - n:
            window.popleft()
        if i >= n:
            out[i] = l[window[0]]
        while window and l[window[-1]] >= value:
            window.pop()
        window.append(i)
    return out


def last_pivot_low(l: list[float], i: int, width: int = 3, lookback: int = 48) -> float | None:  # noqa: E741
    """The most recent swing low confirmed by candle i (the lowest of `width` candles on each side)."""
    for k in range(i - width, max(width, i - lookback) - 1, -1):
        if all(l[k] <= l[j] for j in range(k - width, k + width + 1)):
            return l[k]
    return None


def last_pivot_high(h: list[float], i: int, width: int = 3, lookback: int = 48) -> float | None:
    """The most recent swing high confirmed by candle i."""
    for k in range(i - width, max(width, i - lookback) - 1, -1):
        if all(h[k] >= h[j] for j in range(k - width, k + width + 1)):
            return h[k]
    return None


def levels(h: list[float], l: list[float], i: int, price: float, width: int = 5,  # noqa: E741
           lookback: int = 240) -> tuple[float | None, float | None]:
    """The nearest support (a swing low below the price) and resistance (a swing high above it)."""
    support = resistance = None
    for k in range(i - width, max(width, i - lookback) - 1, -1):
        if all(l[k] <= l[j] for j in range(k - width, k + width + 1)) and l[k] < price:
            support = l[k] if support is None else max(support, l[k])
        if all(h[k] >= h[j] for j in range(k - width, k + width + 1)) and h[k] > price:
            resistance = h[k] if resistance is None else min(resistance, h[k])
    return support, resistance
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_indicators.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orion/trading/indicators.py tests/test_trading_indicators.py
git commit -m "Trading indicators: EMA, RSI, ATR, ADX, channels, pivots, levels"
```

---
### Task 4: Signals — the three strategies

**Files:**
- Create: `orion/trading/signals.py`
- Test: `tests/test_trading_signals.py`

**Interfaces:**
- Consumes: `data.Bars`, `data.HOUR`, `data.DEFAULT_FUNDING`, `indicators.*`, `trading.MEMORY`
- Produces:
  - `PARAMS_FILE`, `STRATEGIES = ("pullback", "breakout", "reversal")`, `LABELS: dict[str, str]`, `DEFAULTS: dict[str, dict]`, `TIME_STOP_HOURS = 48`, `WARMUP = 60`, `DAY`
  - `@dataclass Signal(coin, strategy, side, time, entry, stop, target, strength, reasons)` + `.risk`, `.to_dict()`, `Signal.from_dict(d)`
  - `load_params() -> dict[str, dict]`, `save_params(strategy: str, numbers: dict, why: str) -> None`
  - `@dataclass Prepared(coin, h1, h4, d1, params, funding_t, funding_v, s, i4, i1d, btc_trend, fear_greed, btc_h4=None, fear_greed_raw=[])`
  - `prepare(coin, h1, h4, d1, funding: list[tuple[int, float]], params=None, btc_h4=None, fear_greed=None) -> Prepared`
  - `with_params(p: Prepared, params: dict) -> Prepared`
  - `signals_at(p, i, only: str | None = None) -> list[Signal]`, `latest(p) -> list[Signal]`
  - `funding_rank(p, t_ms) -> float | None`
  - `@dataclass Context(price, trend4, trend1d, support, resistance, low24, high24, funding_rank, atr, time)`; `context(p, i=None) -> Context`; `range_24h(h1: Bars, i: int, days=30) -> tuple[float, float]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_signals.py`:

```python
import copy
import json
import math
import random

import pytest

from orion.trading import data, signals
from orion.trading.data import HOUR, Bars
from orion.trading.signals import DAY

BASE = 100 * DAY


def fake(n=80, coin="BTC", trend4=1, **series):
    """A Prepared with hand-made indicator values: every rule can be steered exactly."""
    h1 = Bars(HOUR, [BASE + k * HOUR for k in range(n)], [100.0] * n, [101.0] * n, [99.0] * n, [100.0] * n,
              [100.0] * n)
    h4 = Bars(4 * HOUR, [BASE - 4 * HOUR], [100.0], [100.0], [100.0], [110.0 if trend4 > 0 else 90.0], [1.0])
    s = {"fast1": [100.0] * n, "slow1": [95.0] * n,
         "fast4": [105.0 if trend4 > 0 else 95.0], "slow4": [100.0],
         "ema50d": [], "ema200d": [], "rsi4": [50.0], "atr1": [1.0] * n, "adx1": [20.0] * n,
         "vol1": [100.0] * n, "hi1": [101.0] * n, "lo1": [99.0] * n}
    s.update(series)
    return signals.Prepared(coin, h1, h4, Bars(DAY), copy.deepcopy(signals.DEFAULTS), [], [], s, [0] * n,
                            [-1] * n, None, [None] * n)


def test_pullback_long_fires_when_the_price_closes_back_above_the_fast_ema():
    p = fake()
    i = len(p.h1) - 1
    p.h1.c[i] = 101.0
    found = signals.signals_at(p, i, only="pullback")
    assert len(found) == 1
    s = found[0]
    assert (s.side, s.strategy, s.entry, s.time) == ("long", "pullback", 101.0, p.h1.end(i))
    assert s.stop == pytest.approx(98.9)          # beyond the swing low 99 (+0.1 ATR), more than 1.5 ATR
    assert s.target == pytest.approx(105.2)       # 2 × the stop distance
    assert s.strength == 1 and s.reasons == ["отскок в тренда"]


def test_no_pullback_long_against_the_4h_trend():
    p = fake(trend4=-1)
    p.h1.c[-1] = 101.0
    assert signals.signals_at(p, len(p.h1) - 1, only="pullback") == []


def test_breakout_long_needs_volume():
    p = fake(hi1=[100.5] * 80, adx1=[20.0] * 79 + [21.0])
    i = 79
    p.h1.c[i], p.h1.v[i] = 101.0, 200.0
    found = signals.signals_at(p, i, only="breakout")
    assert [(s.side, s.strategy) for s in found] == [("long", "breakout")]
    p.h1.v[i] = 120.0
    assert signals.signals_at(p, i, only="breakout") == []


def crowded_funding(p, days=40, rising=True):
    end = p.h1.end(len(p.h1) - 1)
    count = days * 24
    p.funding_t = [end - (count - k) * HOUR for k in range(count + 1)]
    p.funding_v = [(k if rising else count - k) * 1e-6 for k in range(count + 1)]


def test_reversal_short_when_the_crowd_is_long():
    p = fake(rsi4=[80.0])
    i = 79
    p.h1.c[i] = 98.0                                # closes below the previous candle's low (99)
    crowded_funding(p)
    found = signals.signals_at(p, i, only="reversal")
    assert [(s.side, s.strategy) for s in found] == [("short", "reversal")]
    assert found[0].stop == pytest.approx(101.0)   # swing high 101, capped at 3 ATR
    assert found[0].target == pytest.approx(92.0)


def test_reversal_needs_a_month_of_funding_history():
    p = fake(rsi4=[80.0])
    p.h1.c[79] = 98.0
    crowded_funding(p, days=10)
    assert signals.signals_at(p, 79, only="reversal") == []


def test_strength_counts_every_agreeing_factor():
    p = fake(coin="ETH")
    i = 79
    p.h1.c[i], p.h1.v[i] = 101.0, 150.0
    p.d1 = Bars(DAY, [BASE - DAY], [100.0], [100.0], [100.0], [120.0], [1.0])
    p.s["ema50d"], p.s["ema200d"], p.i1d = [110.0], [100.0], [0] * 80
    p.btc_trend = [1] * 80
    crowded_funding(p, rising=False)               # funding now at its lowest: nobody is crowded long
    s = signals.signals_at(p, i, only="pullback")[0]
    assert s.strength == 5
    assert len(s.reasons) == 5


def test_closed_index_never_looks_ahead():
    h1 = Bars(HOUR)
    for k in range(12):
        h1.add(k * HOUR, 1, 1, 1, 1, 1)
    h4 = data.resample(h1, 4 * HOUR)
    assert signals._closed_index(h1, h4) == [-1, -1, -1, 0, 0, 0, 0, 1, 1, 1, 1, 2]


def random_walk(n=3000, seed=7):
    rng = random.Random(seed)
    bars, price = Bars(HOUR), 100.0
    for k in range(n):
        o = price
        price *= math.exp(rng.gauss(0, 0.01))
        hi = max(o, price) * (1 + abs(rng.gauss(0, 0.003)))
        lo = min(o, price) * (1 - abs(rng.gauss(0, 0.003)))
        bars.add(data.HISTORY_START + k * HOUR, o, hi, lo, price, rng.uniform(50, 250))
    return bars


def test_prepare_on_a_random_walk_gives_consistent_signals():
    h1 = random_walk()
    funding = [(t, 0.00001) for t in h1.t]
    p = signals.prepare("BTC", h1, data.resample(h1, 4 * HOUR), data.resample(h1, DAY), funding,
                        copy.deepcopy(signals.DEFAULTS))
    found = [s for i in range(len(h1)) for s in signals.signals_at(p, i)]
    assert found, "a 3000-hour random walk should trigger at least one strategy"
    for s in found:
        if s.side == "long":
            assert s.stop < s.entry < s.target
        else:
            assert s.target < s.entry < s.stop
        assert 1 <= s.strength <= 5
        assert s.target - s.entry == pytest.approx(signals.DEFAULTS[s.strategy]["reward"] * (s.entry - s.stop))
    again = signals.with_params(p, copy.deepcopy(signals.DEFAULTS))
    assert [s.to_dict() for s in signals.signals_at(again, len(h1) - 1)] == \
        [s.to_dict() for s in signals.signals_at(p, len(h1) - 1)]


def test_context_and_the_24h_range():
    h1 = random_walk(400)
    p = signals.prepare("BTC", h1, data.resample(h1, 4 * HOUR), data.resample(h1, DAY), [],
                        copy.deepcopy(signals.DEFAULTS))
    ctx = signals.context(p)
    assert ctx.price == h1.c[-1] and ctx.low24 < ctx.price < ctx.high24
    assert ctx.funding_rank is None
    zigzag = Bars(HOUR)
    for k in range(100):
        zigzag.add(k * HOUR, 1, 1, 1, 100.0 * (1.01 if k % 2 else 1.0), 1)
    low, high = signals.range_24h(zigzag, 99)
    assert high / 101.0 == pytest.approx(math.exp(math.log(1.01) * math.sqrt(24)), rel=0.02)
    assert low / 101.0 == pytest.approx(math.exp(-math.log(1.01) * math.sqrt(24)), rel=0.02)


def test_signal_round_trip():
    s = signals.Signal("SOL", "breakout", "short", 5, 100.0, 101.0, 98.0, 3, ["пробив"])
    assert signals.Signal.from_dict(json.loads(json.dumps(s.to_dict()))) == s
    assert s.risk == 1.0


def test_params_default_then_promoted(monkeypatch, tmp_path):
    monkeypatch.setattr(signals, "PARAMS_FILE", tmp_path / "params.json")
    assert signals.load_params() == signals.DEFAULTS
    new = {**signals.DEFAULTS["pullback"], "fast": 13}
    signals.save_params("pullback", new, "тест")
    assert signals.load_params()["pullback"]["fast"] == 13
    saved = json.loads((tmp_path / "params.json").read_text(encoding="utf-8"))
    assert saved["history"][0]["old"] == signals.DEFAULTS["pullback"] and saved["history"][0]["why"] == "тест"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_signals.py -q`
Expected: FAIL — `ImportError: cannot import name 'signals'`

- [ ] **Step 3: Write the implementation**

Create `orion/trading/signals.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_signals.py -q`
Expected: PASS. If `test_prepare_on_a_random_walk_gives_consistent_signals` finds no signal, change the seed to 11 — the test checks the code paths, not a market claim.

- [ ] **Step 5: Commit**

```bash
git add orion/trading/signals.py tests/test_trading_signals.py
git commit -m "Trading signals: pullback, breakout and reversal strategies with strength and context"
```

---

### Task 5: Market assembly and the honest backtest

**Files:**
- Create: `orion/trading/market.py`, `orion/trading/backtest.py`
- Test: `tests/test_trading_backtest.py`

**Interfaces:**
- Consumes: `data.history/live_bars/funding/recent_funding/fear_greed/resample/HOUR/DEFAULT_FUNDING`, `signals.*`
- Produces:
  - `market.history(coin: str, params: dict | None = None) -> Prepared`, `market.live(coin: str, params: dict | None = None) -> Prepared`
  - `backtest.STATS_FILE`, `FEE = 0.00045`, `SLIPPAGE: dict[str, float]`, `SPLIT = 0.7`, `MIN_TRADES = 30`, `MIN_PROFIT_FACTOR = 1.1`
  - `@dataclass Trade(coin, strategy, side, entry_time, exit_time, entry, exit, stop, target, r, why)`
  - `exit_walk(side, stop, target, bars: Bars, start: int, deadline: int) -> tuple[int, float, str] | None` (why ∈ `"стоп" | "цел" | "време"`)
  - `funding_cost(side, funding_t, funding_v, start_ms, end_ms) -> float`
  - `result_r(coin, side, entry, exit_price, stop, funding_paid) -> float`
  - `simulate(p, strategy, start, end) -> list[Trade]`
  - `@dataclass Stats(trades, win_rate, win_low, win_high, avg_r, profit_factor, max_drawdown_r)` + `.enabled`; `stats(trades) -> Stats`; `wilson(k, n) -> tuple[float, float]`; `Stats.from_dict(d)`
  - `run(coins=COINS, params=None, save=True) -> dict` (report), `load() -> dict | None`, `stale() -> bool`, `is_enabled(report, coin, strategy) -> bool`, `refresh_async(lock=None) -> bool`, `save_lock: threading.Lock | None` (app.py sets it)
  - Report shape: `{"time": ms, "coins": {coin: {"pullback": Stats dict, "breakout": …, "reversal": …, "range": {"hits": int, "total": int}, "from": ms, "to": ms}}}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_backtest.py`:

```python
import copy
import json

import pytest

from orion.trading import backtest, market, signals
from orion.trading.data import HOUR, Bars
from orion.trading.signals import DAY, Signal
from test_trading_signals import random_walk


def bars_from(rows):
    bars = Bars(HOUR)
    for k, (o, h, l, c) in enumerate(rows):
        bars.add(k * HOUR, o, h, l, c, 1.0)
    return bars


def flat(n):
    return [(100.0, 100.5, 99.5, 100.0)] * n


def test_exit_walk_target_stop_and_both_in_one_candle():
    bars = bars_from(flat(3) + [(100.0, 102.5, 99.6, 102.0)])
    assert backtest.exit_walk("long", 99.0, 102.0, bars, 1, 10 ** 12) == (3, 102.0, "цел")
    both = bars_from(flat(3) + [(100.0, 102.5, 98.9, 101.0)])
    assert backtest.exit_walk("long", 99.0, 102.0, both, 1, 10 ** 12) == (3, 99.0, "стоп")
    gap = bars_from(flat(3) + [(98.0, 98.5, 97.0, 98.0)])
    assert backtest.exit_walk("long", 99.0, 102.0, gap, 1, 10 ** 12) == (3, 98.0, "стоп")
    short = bars_from(flat(3) + [(100.0, 100.2, 97.5, 98.0)])
    assert backtest.exit_walk("short", 101.0, 98.0, short, 1, 10 ** 12) == (3, 98.0, "цел")


def test_exit_walk_time_stop_and_still_open():
    bars = bars_from(flat(120))
    k, price, why = backtest.exit_walk("long", 90.0, 110.0, bars, 61, 61 * HOUR + 48 * HOUR)
    assert (k, price, why) == (108, 100.0, "време")
    assert backtest.exit_walk("long", 90.0, 110.0, bars_from(flat(20)), 1, 10 ** 12) is None


def test_costs_in_r():
    assert backtest.result_r("BTC", "long", 100.0, 102.0, 99.0, 0.0) == pytest.approx((0.02 - 0.0013) / 0.01)
    assert backtest.result_r("SOL", "short", 100.0, 101.0, 101.0, 0.0) == pytest.approx((-0.01 - 0.0019) / 0.01)
    t = [0, HOUR, 2 * HOUR]
    v = [0.001, 0.002, 0.003]
    assert backtest.funding_cost("long", t, v, 0, 2 * HOUR) == pytest.approx(0.005)
    assert backtest.funding_cost("short", t, v, 0, 2 * HOUR) == pytest.approx(-0.005)
    assert backtest.funding_cost("long", [], [], 0, 3 * HOUR) == pytest.approx(3 * 0.0000125)


def prepared(h1):
    n = len(h1)
    return signals.Prepared("BTC", h1, Bars(4 * HOUR), Bars(DAY), copy.deepcopy(signals.DEFAULTS), [], [], {},
                            [-1] * n, [-1] * n, None, [None] * n)


def test_simulate_enters_on_the_next_open_and_charges_costs(monkeypatch):
    rows = flat(61) + [(100.0, 100.5, 99.6, 100.2), (100.2, 101.0, 99.8, 100.8), (100.8, 102.5, 100.5, 102.2)]
    rows += flat(10)
    p = prepared(bars_from(rows))
    sig = Signal("BTC", "pullback", "long", p.h1.end(60), 100.0, 99.0, 102.0, 3, ["отскок в тренда"])
    monkeypatch.setattr(signals, "signals_at", lambda p_, i, only=None: [sig] if i == 60 else [])
    trades = backtest.simulate(p, "pullback", 0, len(p.h1))
    assert len(trades) == 1
    t = trades[0]
    assert (t.entry, t.exit, t.why, t.entry_time) == (100.0, 102.0, "цел", 61 * HOUR)
    funding = 3 * 0.0000125
    assert t.r == pytest.approx((0.02 - 0.0013 - funding) / 0.01)


def test_stats_and_the_enable_rule():
    def trades(rs):
        return [backtest.Trade("BTC", "pullback", "long", 0, 0, 1, 1, 1, 1, r, "цел") for r in rs]
    st = backtest.stats(trades([2, -1, -1, 2, -1]))
    assert (st.trades, st.win_rate, st.avg_r) == (5, 0.4, pytest.approx(0.2))
    assert st.profit_factor == pytest.approx(4 / 3) and st.max_drawdown_r == pytest.approx(2.0)
    assert not st.enabled                                    # fewer than 30 trades
    assert backtest.stats(trades([2, -1] * 15)).enabled
    assert not backtest.stats(trades([2, -1, -1] * 10)).enabled  # average 0 R
    low, high = backtest.wilson(5, 10)
    assert low == pytest.approx(0.237, abs=0.01) and high == pytest.approx(0.763, abs=0.01)
    assert backtest.stats([]).trades == 0
    assert backtest.stats(trades([1] * 30)).profit_factor == 99.0     # no losses: capped, JSON-safe


def test_run_reports_out_of_sample_and_saves(monkeypatch, tmp_path):
    monkeypatch.setattr(backtest, "STATS_FILE", tmp_path / "stats.json")
    h1 = random_walk(3000)

    def history(coin, params=None):
        return signals.prepare(coin, h1, backtest.data.resample(h1, 4 * HOUR), backtest.data.resample(h1, DAY),
                               [(t, 0.00001) for t in h1.t], copy.deepcopy(signals.DEFAULTS))

    monkeypatch.setattr(market, "history", history)
    report = backtest.run(coins=("BTC",))
    entry = report["coins"]["BTC"]
    assert set(entry) == {"pullback", "breakout", "reversal", "range", "from", "to"}
    assert entry["from"] == h1.t[int(len(h1) * backtest.SPLIT)]
    assert entry["range"]["total"] > 0
    assert json.loads((tmp_path / "stats.json").read_text(encoding="utf-8")) == report
    assert backtest.load() == report and not backtest.stale()
    assert backtest.is_enabled(report, "BTC", "pullback") == backtest.Stats.from_dict(entry["pullback"]).enabled
    assert backtest.is_enabled(None, "BTC", "pullback") is False


def test_market_live_adds_btc_trend_only_for_other_coins(monkeypatch):
    h1 = random_walk(300)
    calls = []

    def live_bars(coin, interval, count=1000):
        calls.append((coin, interval))
        return h1 if interval == "1h" else backtest.data.resample(h1, 4 * HOUR if interval == "4h" else DAY)

    monkeypatch.setattr(market.data, "live_bars", live_bars)
    monkeypatch.setattr(market.data, "recent_funding", lambda coin, days=90: [])
    monkeypatch.setattr(market.data, "fear_greed", lambda: [])
    assert market.live("BTC").btc_trend is None
    assert ("BTC", "4h") in calls
    calls.clear()
    eth = market.live("ETH")
    assert eth.btc_trend is not None and ("BTC", "4h") in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_backtest.py -q`
Expected: FAIL — `ImportError: cannot import name 'backtest'`

- [ ] **Step 3: Write `orion/trading/market.py`**

```python
"""Puts a coin's data together for the strategies: history (backtest, lab) or live (forecasts, watch, practice)."""
from . import data, signals

H4, D1 = 4 * data.HOUR, 24 * data.HOUR


def _fear_greed() -> list[tuple[int, int]]:
    try:
        return data.fear_greed()
    except OSError:  # the index is a bonus point, not a reason to fail
        return []


def history(coin: str, params: dict | None = None) -> signals.Prepared:
    """Years of Binance 1h candles (4h and 1d built from them) + Hyperliquid funding."""
    h1 = data.history(coin)
    btc_h4 = data.resample(data.history("BTC"), H4) if coin != "BTC" else None
    return signals.prepare(coin, h1, data.resample(h1, H4), data.resample(h1, D1), data.funding(coin), params,
                           btc_h4=btc_h4, fear_greed=_fear_greed())


def live(coin: str, params: dict | None = None) -> signals.Prepared:
    """Hyperliquid's own candles — the prices sir trades at."""
    h1 = data.live_bars(coin, "1h", 1000)
    h4 = data.live_bars(coin, "4h", 600)
    d1 = data.live_bars(coin, "1d", 400)
    btc_h4 = data.live_bars("BTC", "4h", 600) if coin != "BTC" else None
    return signals.prepare(coin, h1, h4, d1, data.recent_funding(coin), params, btc_h4=btc_h4,
                           fear_greed=_fear_greed())
```

- [ ] **Step 4: Write `orion/trading/backtest.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_backtest.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add orion/trading/market.py orion/trading/backtest.py tests/test_trading_backtest.py
git commit -m "Trading backtest: costs, 70/30 out-of-sample report, enable rule; market assembly"
```

---

### Task 6: The live forecast journal

**Files:**
- Create: `orion/trading/journal.py`
- Test: `tests/test_trading_journal.py`

**Interfaces:**
- Consumes: `backtest.exit_walk`, `backtest.result_r`, `data.live_bars`, `data.HOUR`, `signals.Signal`, `signals.TIME_STOP_HOURS`, `risk.OrderPlan` (only its attributes `network, coin, side, entry, stop, target, size`)
- Produces: `JOURNAL`, `add_signal(signal, source: str) -> bool`, `add_trade(plan, strategy: str) -> None`, `close_trade(coin, exit_price=None, pnl=None) -> None`, `open_trade_time(coin) -> int | None`, `resolve(bars_for=None) -> int`, `record(days=7, now_ms=None) -> dict` with keys `days, n, wins, win_rate, avg_r, open, by_strategy{strategy: {n, wins, r}}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_journal.py`:

```python
from types import SimpleNamespace

import pytest

from orion.trading import journal
from orion.trading.data import HOUR, Bars
from orion.trading.signals import Signal


@pytest.fixture(autouse=True)
def temp_journal(monkeypatch, tmp_path):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.json")


def sig(time=10 * HOUR, side="long"):
    return Signal("BTC", "pullback", side, time, 100.0, 99.0, 102.0, 4, ["отскок в тренда"])


def test_a_signal_is_recorded_once_whatever_the_source():
    assert journal.add_signal(sig(), "asked")
    assert not journal.add_signal(sig(), "watch")
    assert journal.add_signal(sig(time=11 * HOUR), "watch")


def candles(rows, start=10 * HOUR):
    bars = Bars(HOUR)
    for k, (o, h, l, c) in enumerate(rows):
        bars.add(start + k * HOUR, o, h, l, c, 1.0)
    return bars


def test_resolve_settles_a_target_and_expires_what_is_too_old():
    journal.add_signal(sig(), "watch")
    journal.add_signal(sig(time=1 * HOUR), "watch")          # older than the candles we get back
    bars = candles([(100.0, 100.5, 99.5, 100.2), (100.2, 102.3, 100.0, 102.0)])
    assert journal.resolve(lambda coin: bars) == 2
    summary = journal.record(days=1, now_ms=12 * HOUR)
    assert (summary["n"], summary["wins"], summary["open"]) == (1, 1, 0)
    assert summary["avg_r"] == pytest.approx((0.02 - 0.0013) / 0.01, abs=1e-3)
    assert summary["by_strategy"]["pullback"]["n"] == 1


def test_open_signals_stay_open_until_a_level_or_48h():
    journal.add_signal(sig(), "watch")
    assert journal.resolve(lambda coin: candles([(100.0, 100.5, 99.5, 100.0)])) == 0
    assert journal.record(days=1, now_ms=12 * HOUR)["open"] == 1


def test_trades_are_tracked_for_the_time_stop():
    plan = SimpleNamespace(network="testnet", coin="ETH", side="short", entry=2000.0, stop=2040.0, target=1920.0,
                           size=0.5)
    journal.add_trade(plan, "пробив")
    assert journal.open_trade_time("ETH") is not None
    journal.close_trade("ETH", 1925.0, 37.5)
    assert journal.open_trade_time("ETH") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_journal.py -q`
Expected: FAIL — `ImportError: cannot import name 'journal'`

- [ ] **Step 3: Write the implementation**

Create `orion/trading/journal.py`:

```python
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


def add_trade(plan, strategy: str) -> None:
    """A real trade sir approved (the network is its source)."""
    with _lock:
        items = _load()
        items.append({"kind": "trade", "source": plan.network, "status": "open", "coin": plan.coin,
                      "side": plan.side, "strategy": strategy, "entry": plan.entry, "stop": plan.stop,
                      "target": plan.target, "size": plan.size, "time": _now()})
        _save(items)


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_journal.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orion/trading/journal.py tests/test_trading_journal.py
git commit -m "Trading journal: every signal and trade with its real outcome"
```

---
### Task 7: Risk — the hard limits

**Files:**
- Create: `orion/trading/risk.py`
- Test: `tests/test_trading_risk.py`

**Interfaces:**
- Consumes: `trading.NAMES`
- Produces:
  - `MIN_NOTIONAL = 10.0`, `FEE = 0.00045`, `class RiskError(Exception)`
  - `@dataclass Limits(risk_pct=2.0, max_leverage=10, daily_loss_pct=6.0, max_positions=3)`
  - `@dataclass AccountState(equity: float, positions: dict[str, dict] = {}, lost_today: float = 0.0)` — position dict keys: `side, size, entry, pnl, liq, value`
  - `@dataclass OrderPlan(coin, side, size, entry, stop, target, leverage, notional, margin, risk_usd, reward_usd, liquidation, fees_usd, network, reduced=False, sz_decimals=0)`
  - `round_price(price, sz_decimals) -> float`, `round_size(size, sz_decimals) -> float`, `maintenance(max_leverage) -> float`, `size_for(equity, entry, stop, limits) -> float`
  - `plan(coin, side, entry, stop, target, account, sz_decimals, coin_max_leverage, limits, network) -> OrderPlan` (raises `RiskError` with a Bulgarian reason)

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_risk.py`:

```python
import pytest

from orion.trading import risk
from orion.trading.risk import AccountState, Limits, RiskError


def make(entry=100.0, stop=99.0, target=102.0, side="long", equity=1000.0, limits=None, positions=None, lost=0.0,
         decimals=5, max_lev=40):
    return risk.plan("BTC", side, entry, stop, target, AccountState(equity, positions or {}, lost), decimals, max_lev,
                     limits or Limits(), "testnet")


def test_a_normal_long_risks_exactly_two_percent():
    p = make()
    assert p.size == 20.0 and p.notional == 2000.0
    assert p.leverage == 6                       # 2000 $ in a third of the account
    assert p.risk_usd == pytest.approx(20.0) and p.reward_usd == pytest.approx(40.0)
    assert p.margin == pytest.approx(2000 / 6)
    assert p.liquidation == pytest.approx(100 * (1 - (1 / 6 - 1 / 80)))
    assert p.fees_usd == pytest.approx(1.8)
    assert not p.reduced and p.network == "testnet"


def test_a_tight_stop_is_capped_by_the_leverage_limit():
    p = make(stop=99.8)
    assert p.leverage == 10 and p.reduced
    assert p.risk_usd == pytest.approx(6.6667, abs=1e-3)


def test_the_liquidation_must_stay_well_beyond_the_stop():
    p = make(stop=92.0, target=116.0, limits=Limits(risk_pct=10, max_leverage=10, daily_loss_pct=50, max_positions=10))
    assert p.leverage == 7 and p.size == 7.0 and p.reduced
    assert p.liquidation < 92.0
    with pytest.raises(RiskError, match="ликвидацията"):
        make(stop=30.0, target=240.0)


def test_a_short():
    p = make(entry=100.0, stop=101.0, target=98.0, side="short")
    assert p.side == "short" and p.liquidation > 101.0 and p.risk_usd == pytest.approx(20.0)


@pytest.mark.parametrize("kwargs, words", [
    ({"stop": 101.0}, "При лонг"),
    ({"side": "short"}, "При шорт"),
    ({"positions": {"BTC": {}}}, "Вече имате позиция в Биткойн"),
    ({"positions": {"ETH": {}, "SOL": {}, "DOGE": {}}}, "лимитът"),
    ({"lost": 60.0}, "заключена до полунощ"),
    ({"lost": 45.0}, "може да мине днешния лимит"),
    ({"equity": 4.0}, "под минимума"),
    ({"equity": 0.0}, "няма пари"),
])
def test_refusals_say_why(kwargs, words):
    with pytest.raises(RiskError, match=words):
        make(**kwargs)


def test_rounding_follows_hyperliquid_rules():
    assert risk.round_price(84467.123, 5) == 84467.0
    assert risk.round_price(2667.054, 4) == 2667.1
    assert risk.round_price(118.4853, 2) == 118.49
    assert risk.round_size(0.123456, 5) == 0.12345
    assert risk.round_size(33.333339, 2) == 33.33
    assert risk.maintenance(40) == 0.0125
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_risk.py -q`
Expected: FAIL — `ImportError: cannot import name 'risk'`

- [ ] **Step 3: Write the implementation**

Create `orion/trading/risk.py`:

```python
"""
Hard limits for every real trade — pure functions, no network. The exchange never gets an order that did
not pass plan(). Defaults (sir chose „агресивен“): ≤2 % of the account lost at the stop, leverage ≤10x,
≤6 % lost per day, ≤3 open positions. Isolated margin; the liquidation must be ≥1.5× further than the stop.
"""
import math
from dataclasses import dataclass, field

from . import NAMES

MIN_NOTIONAL = 10.0     # Hyperliquid's minimum order value, $
FEE = 0.00045           # taker fee per side


class RiskError(Exception):
    """A refusal with a reason Orion says out loud."""


@dataclass
class Limits:
    risk_pct: float = 2.0
    max_leverage: int = 10
    daily_loss_pct: float = 6.0
    max_positions: int = 3


@dataclass
class AccountState:
    equity: float
    positions: dict[str, dict] = field(default_factory=dict)  # coin -> {"side", "size", "entry", "pnl", "liq", "value"}
    lost_today: float = 0.0                                  # $ lost today (realised + fees + funding), ≥ 0


@dataclass
class OrderPlan:
    coin: str
    side: str
    size: float
    entry: float
    stop: float
    target: float
    leverage: int
    notional: float
    margin: float
    risk_usd: float
    reward_usd: float
    liquidation: float
    fees_usd: float
    network: str
    reduced: bool = False       # smaller than 2 % risk because of the leverage or liquidation limit
    sz_decimals: int = 0


def round_price(price: float, sz_decimals: int) -> float:
    """Hyperliquid's price rule for perps: ≤5 significant figures and ≤(6 − szDecimals) decimals."""
    return round(float(f"{price:.5g}"), 6 - sz_decimals)


def round_size(size: float, sz_decimals: int) -> float:
    """Rounded DOWN to the coin's size step — never more risk than planned."""
    step = 10 ** sz_decimals
    return math.floor(size * step + 1e-9) / step


def maintenance(max_leverage: int) -> float:
    """The maintenance margin: half of the initial margin at the coin's max leverage."""
    return 1 / (2 * max_leverage)


def size_for(equity: float, entry: float, stop: float, limits: Limits) -> float:
    """How many coins lose exactly risk_pct of the account at the stop (before rounding and caps)."""
    return equity * limits.risk_pct / 100 / abs(entry - stop)


def plan(coin: str, side: str, entry: float, stop: float, target: float, account: AccountState, sz_decimals: int,
         coin_max_leverage: int, limits: Limits, network: str) -> OrderPlan:
    name = NAMES.get(coin, coin)
    if side == "long" and not stop < entry < target:
        raise RiskError("При лонг стопът трябва да е под цената, а целта — над нея.")
    if side == "short" and not target < entry < stop:
        raise RiskError("При шорт стопът трябва да е над цената, а целта — под нея.")
    if account.equity <= 0:
        raise RiskError("В сметката няма пари за търговия.")
    if coin in account.positions:
        raise RiskError(f"Вече имате позиция в {name}. Първо я затворете.")
    if len(account.positions) >= limits.max_positions:
        raise RiskError(f"Вече имате {len(account.positions)} отворени позиции — това е лимитът.")
    daily_cap = account.equity * limits.daily_loss_pct / 100
    if account.lost_today >= daily_cap:
        raise RiskError("Днешният лимит на загуба е достигнат — търговията е заключена до полунощ.")
    risk_usd = account.equity * limits.risk_pct / 100
    if account.lost_today + risk_usd > daily_cap:
        raise RiskError("Тази сделка може да мине днешния лимит на загуба. Опитайте утре.")

    distance = abs(entry - stop)
    stop_frac = distance / entry
    allowed = max(1, min(limits.max_leverage, coin_max_leverage))
    slot = account.equity / limits.max_positions          # the margin one position may use
    size = size_for(account.equity, entry, stop, limits)
    notional = size * entry
    leverage = max(1, math.ceil(notional / slot - 1e-9))
    reduced = False
    if leverage > allowed:
        leverage, notional, reduced = allowed, slot * allowed, True
    mm = maintenance(coin_max_leverage)
    while 1 / leverage - mm < 1.5 * stop_frac:
        if leverage == 1:
            raise RiskError("Стопът е твърде далеч — ликвидацията би дошла преди него.")
        leverage -= 1
        if notional / leverage > slot:
            notional, reduced = slot * leverage, True
    size = round_size(min(size, notional / entry), sz_decimals)
    notional = size * entry
    if notional < MIN_NOTIONAL:
        raise RiskError(f"Сделката е под минимума от {MIN_NOTIONAL:.0f} долара на Hyperliquid — "
                        f"сметката е твърде малка за този стоп.")
    sign = 1 if side == "long" else -1
    return OrderPlan(coin, side, size, entry, round_price(stop, sz_decimals), round_price(target, sz_decimals),
                     leverage, notional, notional / leverage, size * distance, size * abs(target - entry),
                     entry * (1 - sign * (1 / leverage - mm)), notional * FEE * 2, network, reduced, sz_decimals)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_risk.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orion/trading/risk.py tests/test_trading_risk.py
git commit -m "Trading risk: sizing, leverage, liquidation, daily and position limits"
```

---

### Task 8: Settings — encrypted keys, network, limits

**Files:**
- Create: `orion/trading/settings.py`
- Test: `tests/test_trading_settings.py`

**Interfaces:**
- Consumes: `config.BASE_DIR`, `risk.Limits`
- Produces: `SETTINGS_FILE`, `DEFAULTS`, `load() -> dict`, `save(data) -> None`, `limits() -> Limits`, `network() -> str`, `set_network(net) -> None`, `enabled() -> bool`, `set_enabled(on) -> None`, `account(net) -> tuple[str, str] | None` (address, decrypted key), `save_account(net, address, key) -> str` (raises `ValueError` with a Bulgarian reason), `protect(text) -> str`, `unprotect(token) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_settings.py`:

```python
import sys

import pytest

from orion.trading import settings

ADDRESS = "0x" + "a1" * 20
KEY = "b2" * 32


@pytest.fixture(autouse=True)
def temp_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "trading_settings.json")


def test_defaults_are_the_testnet_and_the_aggressive_limits():
    assert settings.network() == "testnet" and settings.enabled()
    limits = settings.limits()
    assert (limits.risk_pct, limits.max_leverage, limits.daily_loss_pct, limits.max_positions) == (2.0, 10, 6.0, 3)
    assert settings.account("testnet") is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_round_trip_hides_the_text():
    token = settings.protect("0x" + KEY)
    assert KEY not in token
    assert settings.unprotect(token) == "0x" + KEY


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_a_saved_key_is_encrypted_on_disk(tmp_path):
    message = settings.save_account("testnet", ADDRESS, KEY)
    assert "тестовата" in message
    assert KEY not in settings.SETTINGS_FILE.read_text(encoding="utf-8")
    assert settings.account("testnet") == (ADDRESS, "0x" + KEY)
    assert settings.account("mainnet") is None


@pytest.mark.parametrize("address, key, words", [
    (ADDRESS, " ".join(["abandon"] * 12), "думите за възстановяване"),
    ("0x123", KEY, "Адресът"),
    (ADDRESS, "123", "64 знака"),
])
def test_bad_input_is_refused(address, key, words):
    with pytest.raises(ValueError, match=words):
        settings.save_account("testnet", address, key)


def test_network_and_switch_are_saved():
    settings.set_network("mainnet")
    assert settings.network() == "mainnet"
    settings.set_enabled(False)
    assert not settings.enabled()
    settings.set_network("anything else")
    assert settings.network() == "testnet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_settings.py -q`
Expected: FAIL — `ImportError: cannot import name 'settings'`

- [ ] **Step 3: Write the implementation**

Create `orion/trading/settings.py`:

```python
"""
trading_settings.json — the network, the Hyperliquid API keys (encrypted with Windows DPAPI: only this
Windows user on this PC can read them), the limits and the voice hours. Never in GitHub (.gitignore).
The language model has no skill that changes the limits — sir edits them here.
"""
import base64
import ctypes
import json
import re
from ctypes import wintypes

import config

from .risk import Limits

SETTINGS_FILE = config.BASE_DIR / "trading_settings.json"
DEFAULTS = {
    "network": "testnet",
    "enabled": True,
    "accounts": {},
    "limits": {"risk_pct": 2.0, "max_leverage": 10, "daily_loss_pct": 6.0, "max_positions": 3},
    "voice_hours": [8, 23],
    "announce_strength": 4,
}
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")
KEY_RE = re.compile(r"(?:0x)?[0-9a-fA-F]{64}")


def load() -> dict:
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    merged = {**DEFAULTS, **saved}
    merged["limits"] = {**DEFAULTS["limits"], **saved.get("limits", {})}
    merged["accounts"] = dict(saved.get("accounts", {}))
    return merged


def save(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def limits() -> Limits:
    return Limits(**load()["limits"])


def network() -> str:
    return "mainnet" if load()["network"] == "mainnet" else "testnet"


def set_network(net: str) -> None:
    settings = load()
    settings["network"] = "mainnet" if net == "mainnet" else "testnet"
    save(settings)


def enabled() -> bool:
    return bool(load()["enabled"])


def set_enabled(on: bool) -> None:
    settings = load()
    settings["enabled"] = bool(on)
    save(settings)


def account(net: str) -> tuple[str, str] | None:
    """(account address, agent private key) for the network, or None if not connected."""
    entry = load()["accounts"].get(net)
    if not entry:
        return None
    return entry["address"], unprotect(entry["key"])


def save_account(net: str, address: str, key: str) -> str:
    address, key = address.strip(), key.strip()
    if len(key.split()) >= 12:
        raise ValueError("Това прилича на думите за възстановяване на портфейла. Никога не ги давайте — нито на "
                         "мен, нито на никого. Трябва ми само API ключът от страницата API на Hyperliquid.")
    if not ADDRESS_RE.fullmatch(address):
        raise ValueError("Адресът трябва да започва с 0x и да има 40 знака след това.")
    if not KEY_RE.fullmatch(key):
        raise ValueError("API ключът трябва да е 64 знака (цифри и букви от a до f), по желание с 0x отпред.")
    key = key if key.startswith("0x") else "0x" + key
    settings = load()
    settings["accounts"][net] = {"address": address, "key": protect(key)}
    save(settings)
    return f"Запазих API ключа за {'истинската мрежа' if net == 'mainnet' else 'тестовата мрежа'}."


# --- Windows DPAPI ------------------------------------------------------------------------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(function, data: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    if not function(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):  # UI_FORBIDDEN
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def protect(text: str) -> str:
    return base64.b64encode(_dpapi(ctypes.windll.crypt32.CryptProtectData, text.encode())).decode()


def unprotect(token: str) -> str:
    return _dpapi(ctypes.windll.crypt32.CryptUnprotectData, base64.b64decode(token)).decode()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_settings.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orion/trading/settings.py tests/test_trading_settings.py
git commit -m "Trading settings: DPAPI-encrypted API keys, network, limits"
```

---

### Task 9: Exchange — orders with approval, protection, testnet check

**Files:**
- Create: `orion/trading/exchange.py`
- Test: `tests/test_trading_exchange.py`

**Interfaces:**
- Consumes: `orion.confirm.ask(title, summary, body, accept) -> bool`, `settings.account`, `risk.OrderPlan/AccountState/round_price`, `markets._fmt`
- Produces:
  - `blocked: bool`, `last_open: set[str]`, `SETTLE: float`, `MOVE_LIMIT = 0.003`
  - `class TradingError(Exception)`, `class PriceMoved(Exception)` with `.price`
  - `client_factory: Callable[[str], tuple[info, exchange, address]]` (tests replace it)
  - `account_state(network) -> tuple[AccountState, dict[str, dict]]` — second item `{coin: {"mid", "sz_decimals", "max_leverage"}}`
  - `place(plan, note="") -> str` (may raise `PriceMoved`, `TradingError`)
  - `close(coins: list[str], network, reason="") -> str`
  - `move_stop_to_entry(coin, network) -> str`
  - `fills_since(network, since_ms) -> list[dict]`
  - `check_connection(network) -> str`
  - `testnet_check() -> str`
  - `confirmation(plan, note) -> tuple[str, str, str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_exchange.py`:

```python
import pytest

from orion import confirm
from orion.trading import exchange, risk


class FakeInfo:
    def __init__(self):
        self.mid = 100.0
        self.positions: list[dict] = []
        self.orders: list[dict] = []
        self.fills: list[dict] = []

    def all_mids(self):
        return {"BTC": str(self.mid), "ETH": "2000", "SOL": "100"}

    def user_state(self, address):
        return {"marginSummary": {"accountValue": "1000"},
                "assetPositions": [{"position": p} for p in self.positions]}

    def frontend_open_orders(self, address):
        return list(self.orders)

    def user_fills_by_time(self, address, since):
        return list(self.fills)

    def user_funding_history(self, address, since):
        return [{"delta": {"usdc": "-0.5"}}]

    def meta(self):
        return {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
                             {"name": "ETH", "szDecimals": 4, "maxLeverage": 25},
                             {"name": "SOL", "szDecimals": 2, "maxLeverage": 20}]}

    def extra_agents(self, address):
        return [{"name": "orion", "address": "0xAGENT", "validUntil": 1900000000000}]


class FakeExchange:
    def __init__(self, info, place_stop=True):
        self.info, self.place_stop, self.calls = info, place_stop, []
        self.wallet = type("W", (), {"address": "0xagent"})()

    def _add_trigger(self, order):
        if order["order_type"]["trigger"]["tpsl"] == "sl" and not self.place_stop:
            return
        self.info.orders.append({"coin": order["coin"], "isTrigger": True, "reduceOnly": True,
                                 "triggerPx": str(order["order_type"]["trigger"]["triggerPx"]),
                                 "oid": len(self.info.orders) + 1})

    def update_leverage(self, leverage, coin, is_cross=True):
        self.calls.append(("leverage", coin, leverage, is_cross))
        return {"status": "ok"}

    def bulk_orders(self, orders, grouping="na"):
        self.calls.append(("bulk", orders, grouping))
        entry = orders[0]
        size = entry["sz"] if entry["is_buy"] else -entry["sz"]
        self.info.positions.append({"coin": entry["coin"], "szi": str(size), "entryPx": str(self.info.mid),
                                    "unrealizedPnl": "0", "positionValue": str(abs(size) * self.info.mid)})
        for order in orders[1:]:
            self._add_trigger(order)
        return {"status": "ok", "response": {"type": "order", "data": {"statuses": [
            {"filled": {"totalSz": str(entry["sz"]), "avgPx": str(self.info.mid), "oid": 1}},
            "waitingForFill", "waitingForFill"]}}}

    def order(self, coin, is_buy, sz, limit_px, order_type, reduce_only=False):
        order = {"coin": coin, "is_buy": is_buy, "sz": sz, "limit_px": limit_px, "order_type": order_type}
        self.calls.append(("order", order))
        self._add_trigger(order)
        return {"status": "ok"}

    def market_close(self, coin, sz=None, px=None, slippage=0.05):
        self.calls.append(("close", coin))
        self.info.positions = [p for p in self.info.positions if p["coin"] != coin]
        return {"status": "ok"}

    def cancel(self, coin, oid):
        self.calls.append(("cancel", coin, oid))
        self.info.orders = [o for o in self.info.orders if o["oid"] != oid]
        return {"status": "ok"}


@pytest.fixture
def fake(monkeypatch):
    info = FakeInfo()
    ex = FakeExchange(info)
    used = []
    monkeypatch.setattr(exchange, "client_factory", lambda network: (used.append(network), (info, ex, "0xme"))[1])
    monkeypatch.setattr(exchange, "SETTLE", 0)
    monkeypatch.setattr(exchange, "blocked", False)
    monkeypatch.setattr(exchange, "last_open", set())
    ex.used = used
    return info, ex


@pytest.fixture
def approve(monkeypatch):
    asked = []

    def set_answer(answer):
        monkeypatch.setattr(confirm, "handler", lambda *args: (asked.append(args), answer)[1])
        return asked
    return set_answer


def plan(side="long", entry=100.0, stop=99.0, target=102.0):
    return risk.plan("BTC", side, entry, stop, target, risk.AccountState(1000.0), 5, 40, risk.Limits(), "testnet")


def test_nothing_is_sent_without_approval(fake, approve):
    info, ex = fake
    asked = approve(False)
    answer = exchange.place(plan())
    assert "не е отворена" in answer
    assert ex.calls == [] and info.positions == []
    title, summary, body, accept = asked[0]
    assert "ТЕСТОВА МРЕЖА" in title and "ЛОНГ" in summary and "Стоп" in body and accept == "Одобри сделката"


def test_an_approved_trade_has_entry_stop_and_target_in_one_group(fake, approve):
    info, ex = fake
    approve(True)
    answer = exchange.place(plan())
    assert answer.startswith("Отворих лонг на Биткойн")
    assert ex.calls[0] == ("leverage", "BTC", 6, False)
    kind, orders, grouping = ex.calls[1]
    assert (kind, grouping) == ("bulk", "normalTpsl")
    entry, tp, sl = orders
    assert entry["order_type"] == {"limit": {"tif": "Ioc"}} and entry["is_buy"] and not entry["reduce_only"]
    assert entry["limit_px"] == 100.5
    assert tp["order_type"]["trigger"] == {"triggerPx": 102.0, "isMarket": True, "tpsl": "tp"} and tp["reduce_only"]
    assert sl["order_type"]["trigger"] == {"triggerPx": 99.0, "isMarket": True, "tpsl": "sl"} and not sl["is_buy"]
    assert exchange.last_open == {"BTC"}


def test_a_price_move_cancels_and_asks_again(fake, approve):
    info, ex = fake
    approve(True)
    info.mid = 100.5
    with pytest.raises(exchange.PriceMoved) as moved:
        exchange.place(plan())
    assert moved.value.price == 100.5 and ex.calls == []


def test_a_missing_stop_closes_the_position_at_once(fake, approve):
    info, ex = fake
    ex.place_stop = False
    approve(True)
    with pytest.raises(exchange.TradingError, match="Стопът не се постави"):
        exchange.place(plan())
    assert ("close", "BTC") in ex.calls and info.positions == []
    assert sum(1 for c in ex.calls if c[0] == "order") == 1      # one retry of the stop


def test_blocked_in_test_mode(fake, monkeypatch):
    info, ex = fake
    monkeypatch.setattr(exchange, "blocked", True)
    with pytest.raises(exchange.TradingError, match="тест режим"):
        exchange.place(plan())
    assert ex.used == []


def test_close_asks_then_closes_and_cancels(fake, approve):
    info, ex = fake
    info.positions = [{"coin": "BTC", "szi": "0.5", "entryPx": "100", "unrealizedPnl": "3.2"}]
    info.orders = [{"coin": "BTC", "isTrigger": True, "reduceOnly": True, "triggerPx": "99", "oid": 7}]
    approve(False)
    assert "остават отворени" in exchange.close(["BTC"], "testnet")
    assert ex.calls == []
    approve(True)
    answer = exchange.close(["BTC", "ETH"], "testnet")
    assert answer.startswith("Затворих: Биткойн (+3.20 $)")
    assert ("close", "BTC") in ex.calls and ("cancel", "BTC", 7) in ex.calls
    assert "Нямате отворена позиция" in exchange.close(["ETH"], "testnet")


def test_account_state_counts_todays_losses(fake):
    info, ex = fake
    info.positions = [{"coin": "ETH", "szi": "-0.5", "entryPx": "2000", "unrealizedPnl": "-4",
                       "liquidationPx": "2300", "positionValue": "1000"}]
    info.fills = [{"closedPnl": "-30", "fee": "1"}, {"closedPnl": "0", "fee": "0.5"}]
    state, coins = exchange.account_state("testnet")
    assert state.equity == 1000.0 and state.lost_today == pytest.approx(32.0)
    assert state.positions["ETH"]["side"] == "short" and state.positions["ETH"]["size"] == 0.5
    assert coins["SOL"] == {"mid": 100.0, "sz_decimals": 2, "max_leverage": 20}
    assert exchange.last_open == {"ETH"}


def test_move_stop_to_entry_only_in_profit(fake, approve):
    info, ex = fake
    info.positions = [{"coin": "BTC", "szi": "0.5", "entryPx": "100", "unrealizedPnl": "1"}]
    info.orders = [{"coin": "BTC", "isTrigger": True, "reduceOnly": True, "triggerPx": "98", "oid": 3}]
    info.mid = 99.0
    assert "още не е на печалба" in exchange.move_stop_to_entry("BTC", "testnet")
    info.mid = 103.0
    approve(True)
    answer = exchange.move_stop_to_entry("BTC", "testnet")
    assert "на входа" in answer
    stops = [o for o in info.orders if float(o["triggerPx"]) <= 100]
    assert [float(o["triggerPx"]) for o in stops] == [100.0]


def test_testnet_check_always_uses_the_testnet(fake, monkeypatch):
    info, ex = fake
    monkeypatch.setattr(exchange, "blocked", True)          # test mode's sandbox does not matter here
    answer = exchange.testnet_check()
    assert ex.used == ["testnet"] and answer.startswith("Проверката в тестовата мрежа мина")
    assert info.positions == [] and info.orders == []


def test_testnet_check_leaves_an_existing_position_alone(fake):
    info, ex = fake
    info.positions = [{"coin": "BTC", "szi": "0.1", "entryPx": "100", "unrealizedPnl": "0"}]
    assert "вече има позиция" in exchange.testnet_check()
    assert ex.calls == []


def test_check_connection_knows_the_agent(fake):
    info, ex = fake
    assert "1000.00 долара" in exchange.check_connection("testnet")
    info.extra_agents = lambda address: []
    assert "не го познава" in exchange.check_connection("testnet")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_exchange.py -q`
Expected: FAIL — `ImportError: cannot import name 'exchange'`

- [ ] **Step 3: Write the implementation**

Create `orion/trading/exchange.py`:

```python
"""
The only place that talks to Hyperliquid with a key. Every open and every close passes through
confirm.ask (sir's „Одобри“) HERE — not in the skills — so no skill, including code Orion writes itself,
can trade without sir. The agent (API) key can trade but cannot withdraw.

After approval the price is read again (moved > 0.3 % -> PriceMoved, the skill proposes again), isolated
leverage is set, and the entry goes in one group with the take-profit and the stop-loss. A position is
never left without a stop: if the stop cannot be placed, the position is closed at once.
"""
import math
import time
from datetime import datetime
from typing import Callable

from .. import confirm
from ..markets import _fmt
from . import COINS, NAMES, risk, settings

MOVE_LIMIT = 0.003          # the price may move this much between the proposal and the click
ENTRY_SLIPPAGE = 0.005
TRIGGER_SLIPPAGE = 0.10     # worst price of a stop/target market order
CLOSE_SLIPPAGE = 0.01
SETTLE = 1.0                # seconds for the exchange to show new orders
blocked = False             # test mode's sandbox sets it: no exchange calls at all
last_open: set[str] = set()  # coins with open positions at the last check (reflexes, watcher)


class TradingError(Exception):
    """A failure with a Bulgarian message Orion says."""


class PriceMoved(Exception):
    def __init__(self, price: float):
        super().__init__(price)
        self.price = price


def _make_client(network: str):
    """(info, exchange, account address) — the SDK is imported only here."""
    import eth_account
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants
    found = settings.account(network)
    if not found:
        raise TradingError("Hyperliquid не е свързан. Кажете „свържи Hyperliquid“.")
    address, key = found
    url = constants.MAINNET_API_URL if network == "mainnet" else constants.TESTNET_API_URL
    client = Exchange(eth_account.Account.from_key(key), url, account_address=address)
    return client.info, client, address


client_factory: Callable = _make_client


def _client(network: str):
    if blocked:
        raise TradingError("В тест режим не стигам до борсата.")
    return client_factory(network)


def _human(text) -> str:
    text = str(text)
    if "does not exist" in text:
        return "API ключът не е одобрен или е изтекъл — направете нов на страницата API на Hyperliquid."
    if "margin" in text.lower():
        return "Няма достатъчно пари (марджин) в сметката за тази сделка."
    return f"Борсата отказа: {text}"


def _ok(result, what: str) -> None:
    if not isinstance(result, dict) or result.get("status") != "ok":
        detail = result.get("response") if isinstance(result, dict) else result
        raise TradingError(f"{what}: {_human(detail)}")


# --- Reading the account -----------------------------------------------------------------------
def _day_start_ms() -> int:
    now = datetime.now()
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


def account_state(network: str) -> tuple[risk.AccountState, dict[str, dict]]:
    """The account now and each coin's order rules {coin: {"mid", "sz_decimals", "max_leverage"}}."""
    info, _, address = _client(network)
    state = info.user_state(address)
    positions = {}
    for item in state.get("assetPositions", []):
        p = item["position"]
        size = float(p["szi"])
        if size:
            positions[p["coin"]] = {"side": "long" if size > 0 else "short", "size": abs(size),
                                    "entry": float(p["entryPx"]), "pnl": float(p.get("unrealizedPnl") or 0),
                                    "liq": float(p.get("liquidationPx") or 0),
                                    "value": float(p.get("positionValue") or 0)}
    since = _day_start_ms()
    realised = sum(float(f.get("closedPnl") or 0) - float(f.get("fee") or 0)
                   for f in info.user_fills_by_time(address, since))
    funding = sum(float(f["delta"].get("usdc") or 0) for f in info.user_funding_history(address, since))
    last_open.clear()
    last_open.update(positions)
    mids = info.all_mids()
    coins = {u["name"]: {"mid": float(mids[u["name"]]), "sz_decimals": int(u["szDecimals"]),
                         "max_leverage": int(u["maxLeverage"])}
             for u in info.meta()["universe"] if u["name"] in COINS and u["name"] in mids}
    return risk.AccountState(float(state["marginSummary"]["accountValue"]), positions,
                             max(0.0, -(realised + funding))), coins


def _position(info, address: str, coin: str) -> dict | None:
    for item in info.user_state(address).get("assetPositions", []):
        p = item["position"]
        size = float(p["szi"])
        if p["coin"] == coin and size:
            return {"side": "long" if size > 0 else "short", "size": abs(size), "entry": float(p["entryPx"]),
                    "pnl": float(p.get("unrealizedPnl") or 0)}
    return None


def _protection(info, address: str, coin: str, side: str, entry: float) -> tuple[list[dict], list[dict]]:
    """(stops, targets): the coin's reduce-only trigger orders, told apart by price — not by their name."""
    stops, targets = [], []
    for order in info.frontend_open_orders(address):
        if order.get("coin") != coin or not order.get("isTrigger") or not order.get("reduceOnly"):
            continue
        below = float(order["triggerPx"]) < entry
        (stops if below == (side == "long") else targets).append(order)
    return stops, targets


# --- Orders -------------------------------------------------------------------------------------
def _trigger(coin: str, is_buy: bool, size: float, price: float, kind: str, sz_decimals: int) -> dict:
    worst = price * (1 + TRIGGER_SLIPPAGE if is_buy else 1 - TRIGGER_SLIPPAGE)
    return {"coin": coin, "is_buy": is_buy, "sz": size, "limit_px": risk.round_price(worst, sz_decimals),
            "order_type": {"trigger": {"triggerPx": risk.round_price(price, sz_decimals), "isMarket": True,
                                       "tpsl": kind}},
            "reduce_only": True}


def _place_trigger(client, coin, is_buy, size, price, kind, sz_decimals):
    order = _trigger(coin, is_buy, size, price, kind, sz_decimals)
    return client.order(order["coin"], order["is_buy"], order["sz"], order["limit_px"], order["order_type"],
                        reduce_only=True)


def _send(info, client, address: str, plan: risk.OrderPlan, mid: float) -> dict | None:
    """Leverage + entry with take-profit and stop in one group. Returns the position (None: not filled)."""
    _ok(client.update_leverage(plan.leverage, plan.coin, is_cross=False), "Ливъриджът")
    buy = plan.side == "long"
    entry_px = risk.round_price(mid * (1 + ENTRY_SLIPPAGE if buy else 1 - ENTRY_SLIPPAGE), plan.sz_decimals)
    orders = [{"coin": plan.coin, "is_buy": buy, "sz": plan.size, "limit_px": entry_px,
               "order_type": {"limit": {"tif": "Ioc"}}, "reduce_only": False},
              _trigger(plan.coin, not buy, plan.size, plan.target, "tp", plan.sz_decimals),
              _trigger(plan.coin, not buy, plan.size, plan.stop, "sl", plan.sz_decimals)]
    result = client.bulk_orders(orders, grouping="normalTpsl")
    _ok(result, "Поръчката")
    first = result["response"]["data"]["statuses"][0]
    if isinstance(first, dict) and "error" in first:
        raise TradingError(_human(first["error"]))
    time.sleep(SETTLE)
    return _position(info, address, plan.coin)


def _protect(info, client, address: str, plan: risk.OrderPlan, position: dict) -> None:
    """Makes sure the stop exists (a missing target is placed once). No stop after a retry -> close now."""
    buy_to_close = position["side"] == "short"
    stops, targets = _protection(info, address, plan.coin, position["side"], position["entry"])
    if not targets:
        _place_trigger(client, plan.coin, buy_to_close, position["size"], plan.target, "tp", plan.sz_decimals)
    if stops:
        return
    _place_trigger(client, plan.coin, buy_to_close, position["size"], plan.stop, "sl", plan.sz_decimals)
    time.sleep(SETTLE)
    stops, _ = _protection(info, address, plan.coin, position["side"], position["entry"])
    if stops:
        return
    client.market_close(plan.coin, slippage=CLOSE_SLIPPAGE)
    last_open.discard(plan.coin)
    raise TradingError("Стопът не се постави, затова затворих позицията веднага.")


def _network_word(network: str) -> str:
    return "ТЕСТОВА МРЕЖА" if network == "testnet" else "РЕАЛНИ ПАРИ"


def confirmation(plan: risk.OrderPlan, note: str = "") -> tuple[str, str, str]:
    """(title, summary, body) of the approval dialog — every number sir needs."""
    side = "ЛОНГ" if plan.side == "long" else "ШОРТ"
    move = lambda price: f"{(price / plan.entry - 1) * 100:+.2f} %"  # noqa: E731
    lines = [
        f"Вход ≈ {_fmt(plan.entry)} $  ·  размер {plan.size:g} {plan.coin} ({plan.notional:,.2f} $)",
        f"Стоп {_fmt(plan.stop)} ({move(plan.stop)}) → загуба ≈ {plan.risk_usd:,.2f} $",
        f"Цел {_fmt(plan.target)} ({move(plan.target)}) → печалба ≈ {plan.reward_usd:,.2f} $",
        f"Ливъридж {plan.leverage}x, изолиран марджин {plan.margin:,.2f} $",
        f"Ликвидация ≈ {_fmt(plan.liquidation)} $  ·  такси ≈ {plan.fees_usd:,.2f} $",
        "Стопът и целта се поставят в борсата — работят и при изключен компютър.",
    ]
    if note:
        lines.append(note)
    return (f"Сделка · {_network_word(plan.network)}",
            f"{side} {NAMES[plan.coin]}: {plan.size:g} ({plan.notional:,.0f} $), {plan.leverage}x",
            "\n".join(lines))


def place(plan: risk.OrderPlan, note: str = "") -> str:
    """Asks sir; on „Одобри“ opens the position with its stop and target. Returns what Orion says."""
    info, client, address = _client(plan.network)
    title, summary, body = confirmation(plan, note)
    if not confirm.ask(title, summary, body, "Одобри сделката"):
        return "Добре, сър — сделката не е отворена."
    mid = float(info.all_mids()[plan.coin])
    if abs(mid / plan.entry - 1) > MOVE_LIMIT:
        raise PriceMoved(mid)
    position = _send(info, client, address, plan, mid)
    if not position:
        return "Входът не се изпълни — цената избяга. Нищо не е отворено."
    _protect(info, client, address, plan, position)
    last_open.add(plan.coin)
    return (f"Отворих {'лонг' if plan.side == 'long' else 'шорт'} на {NAMES[plan.coin]}: {position['size']:g} на "
            f"{_fmt(position['entry'])}. Стоп {_fmt(plan.stop)}, цел {_fmt(plan.target)} — и двата са в борсата.")


def close(coins: list[str], network: str, reason: str = "") -> str:
    """Asks sir, then closes the positions at market and cancels their stops and targets."""
    info, client, address = _client(network)
    open_now = {item["position"]["coin"]: item["position"] for item in info.user_state(address).get("assetPositions", [])
                if float(item["position"]["szi"])}
    wanted = [coin for coin in coins if coin in open_now]
    if not wanted:
        return "Нямате отворена позиция" + (f" в {NAMES.get(coins[0], coins[0])}." if len(coins) == 1 else ".")
    pnl = {coin: float(open_now[coin].get("unrealizedPnl") or 0) for coin in wanted}
    lines = [f"{NAMES[c]}: {'лонг' if float(open_now[c]['szi']) > 0 else 'шорт'} {abs(float(open_now[c]['szi'])):g}, "
             f"сега {pnl[c]:+.2f} $" for c in wanted]
    if not confirm.ask(f"Затваряне · {_network_word(network)}", ", ".join(NAMES[c] for c in wanted),
                       "\n".join(([reason] if reason else []) + lines), "Затвори"):
        return "Добре, сър — позициите остават отворени."
    done = []
    for coin in wanted:
        _ok(client.market_close(coin, slippage=CLOSE_SLIPPAGE), f"Затварянето на {NAMES[coin]}")
        for order in info.frontend_open_orders(address):
            if order.get("coin") == coin and order.get("reduceOnly"):
                client.cancel(coin, order["oid"])
        last_open.discard(coin)
        done.append(f"{NAMES[coin]} ({pnl[coin]:+.2f} $)")
    return "Затворих: " + ", ".join(done) + "."


def move_stop_to_entry(coin: str, network: str) -> str:
    """Moves the stop to the entry price (never further away) — only when the trade is in profit."""
    info, client, address = _client(network)
    position = _position(info, address, coin)
    if not position:
        return f"Нямате позиция в {NAMES[coin]}."
    mid = float(info.all_mids()[coin])
    long = position["side"] == "long"
    if not (mid > position["entry"] if long else mid < position["entry"]):
        return "Цената още не е на печалба — стоп на входа би затворил сделката веднага. Оставям го."
    decimals = next(int(u["szDecimals"]) for u in info.meta()["universe"] if u["name"] == coin)
    entry = risk.round_price(position["entry"], decimals)
    if not confirm.ask(f"Стоп на входа · {_network_word(network)}", f"{NAMES[coin]}: стоп → {_fmt(entry)}",
                       "Ако цената се върне до входа, сделката се затваря без загуба (без таксите).", "Премести стопа"):
        return "Добре, сър — стопът остава където е."
    old, _ = _protection(info, address, coin, position["side"], position["entry"])
    _ok(_place_trigger(client, coin, not long, position["size"], entry, "sl", decimals), "Новият стоп")
    for order in old:
        client.cancel(coin, order["oid"])
    return f"Преместих стопа на {NAMES[coin]} на входа — {_fmt(entry)}."


def fills_since(network: str, since_ms: int) -> list[dict]:
    info, _, address = _client(network)
    return info.user_fills_by_time(address, since_ms)


def check_connection(network: str) -> str:
    """After a key is saved: is it an approved agent of this address, and how much is in the account."""
    info, client, address = _client(network)
    value = float(info.user_state(address)["marginSummary"]["accountValue"])
    agent = client.wallet.address.lower()
    try:
        known = any(str(a.get("address", "")).lower() == agent for a in info.extra_agents(address))
    except Exception:  # noqa: BLE001 — an older API without the list: the first order will tell
        known = True
    where = "тестовата мрежа" if network == "testnet" else "истинската мрежа"
    if not known:
        return (f"Hyperliquid не го познава като одобрен API ключ за този адрес в {where}. Проверете адреса и "
                f"одобряването на страницата API.")
    return f"Свързах се с Hyperliquid в {where}. В сметката има {value:.2f} долара."


def testnet_check() -> str:
    """Test mode's daily check: the smallest BTC long on the TESTNET, its stop and target verified, then
    closed. Always the testnet (the network is fixed here), even while the sandbox blocks everything else."""
    info, client, address = client_factory("testnet")
    if _position(info, address, "BTC"):
        return "Проверката в тестовата мрежа е пропусната — там вече има позиция в биткойн."
    decimals = next(int(u["szDecimals"]) for u in info.meta()["universe"] if u["name"] == "BTC")
    mid = float(info.all_mids()["BTC"])
    size = math.ceil(11 / mid * 10 ** decimals) / 10 ** decimals
    plan = risk.OrderPlan("BTC", "long", size, mid, risk.round_price(mid * 0.98, decimals),
                          risk.round_price(mid * 1.02, decimals), 1, size * mid, size * mid, 0.0, 0.0, 0.0, 0.0,
                          "testnet", sz_decimals=decimals)
    ok = False
    try:
        position = _send(info, client, address, plan, mid)
        if not position:
            return "Проверката в тестовата мрежа: входът не се изпълни."
        stops, targets = _protection(info, address, "BTC", "long", position["entry"])
        ok = bool(stops) and bool(targets)
    finally:
        if _position(info, address, "BTC"):
            client.market_close("BTC", slippage=CLOSE_SLIPPAGE)
        for order in info.frontend_open_orders(address):
            if order.get("coin") == "BTC" and order.get("reduceOnly"):
                client.cancel("BTC", order["oid"])
    if ok:
        return "Проверката в тестовата мрежа мина: входът, стопът и целта се поставиха и позицията се затвори."
    return "Проверката в тестовата мрежа НЕ мина: стопът или целта липсваха. Позицията е затворена."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_exchange.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orion/trading/exchange.py tests/test_trading_exchange.py
git commit -m "Trading exchange: approval inside, entry with stop and target, protection check, testnet check"
```

---
### Task 10: What Orion says, and the trading skills

**Files:**
- Create: `orion/trading/texts.py`, `skills/crypto_trading_skills.py`
- Test: `tests/test_trading_skills.py`

**Interfaces:**
- Consumes: everything above; `markets.Series/analyze/chart_data/_fmt`; `orion.confirm.ask`; `trading.show_key_dialog`
- Produces:
  - `texts`: `SIDE`, `TREND`, `NOT_ADVICE`, `NO_DATA`, `NO_REPORT`, `CONNECT_STEPS: dict[str, str]`, `MAINNET_WARNING`, `pct(x)`, `period(report, coin)`, `best(found, report) -> Signal`, `strategy_line(report, coin, strategy)`, `forecast(coin, found, ctx, report)`, `signal_line(coin, found, report)`, `strategy_table(report)`, `record_text(summary)`, `positions_text(state, network)`, `account_text(state, network, limits)`, `signal_alert(signal, report)`, `fill_text(fill)`
  - Skills (names are what reflexes, router, brain and tests use): `crypto_forecast(coin)`, `crypto_signals()`, `strategy_report()`, `forecast_record(days=7)`, `trading_positions()`, `trading_account()`, `open_trade(coin, side)`, `close_trade(coin)`, `move_stop_to_entry(coin)`, `connect_hyperliquid(network="testnet")`, `pause_trading()`, `resume_trading()`, `switch_trading_network(network)`
  - Module attribute `last_chart: dict | None` (app.py shows it after `crypto_forecast`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_skills.py`:

```python
import copy
import sys

import pytest

import config
from orion import confirm, trading
from orion.tools import registry
from orion.trading import data, exchange, risk, signals
from orion.trading.signals import Signal
from test_trading_signals import random_walk


@pytest.fixture
def cts(monkeypatch, tmp_path):
    if not registry.names():
        registry.load_skills(config.SKILLS_DIR)
    module = sys.modules["skills.crypto_trading_skills"]
    monkeypatch.setattr(module.journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(module.settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(module.backtest, "load", lambda: None)
    monkeypatch.setattr(module.backtest, "refresh_async", lambda lock=None: True)
    h1 = random_walk(1200)
    prepared = signals.prepare("BTC", h1, data.resample(h1, 4 * data.HOUR), data.resample(h1, 24 * data.HOUR), [],
                               copy.deepcopy(signals.DEFAULTS))
    monkeypatch.setattr(module.market, "live", lambda coin, params=None: prepared)
    module.prepared = prepared
    return module


def long_signal(entry=84000.0, stop=83000.0, target=86000.0):
    return Signal("BTC", "pullback", "long", 1, entry, stop, target, 4, ["отскок в тренда", "обемът е над средния"])


def test_a_forecast_with_a_signal(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [long_signal()])
    text = cts.crypto_forecast("биткойна")
    assert "Сигнал ЛОНГ — отскок в тренда, сила 4 от 5" in text
    assert "Защо: обемът е над средния." in text
    assert cts.texts.NO_REPORT in text and text.endswith(cts.texts.NOT_ADVICE)
    assert cts.last_chart["entry"] == 84000.0 and cts.last_chart["stop"] == 83000.0
    assert cts.journal.record(days=1)["open"] == 1


def test_a_forecast_without_a_signal_gives_the_24h_range(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [])
    text = cts.crypto_forecast("BTC")
    assert "Няма ясен сигнал" in text and "До 24 часа цената вероятно ще е между" in text


def test_no_data_means_no_forecast(cts, monkeypatch):
    def down(coin, params=None):
        raise OSError("no route")
    monkeypatch.setattr(cts.market, "live", down)
    assert cts.crypto_forecast("биткойн") == cts.texts.NO_DATA


def test_other_coins(cts):
    assert "само биткойн, етериум и солана" in cts.crypto_forecast("доги")


def account(mid):
    return lambda network: (risk.AccountState(1000.0), {"BTC": {"mid": mid, "sz_decimals": 5, "max_leverage": 40}})


def test_open_trade_re_anchors_the_signal_to_the_trading_network_price(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [long_signal()])
    monkeypatch.setattr(cts.exchange, "account_state", account(60000.0))     # the testnet price is far away
    placed = []
    monkeypatch.setattr(cts.exchange, "place", lambda plan, note="": (placed.append((plan, note)), "Отворих лонг")[1])
    assert cts.open_trade("биткойн", "лонг") == "Отворих лонг"
    plan, note = placed[0]
    assert (plan.entry, plan.stop, plan.target, plan.network) == (60000.0, 59000.0, 62000.0, "testnet")
    assert "отскок в тренда" in note
    assert cts.journal.open_trade_time("BTC") is not None


def test_open_trade_without_a_signal_warns_and_uses_atr(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [])
    monkeypatch.setattr(cts.exchange, "account_state", account(100.0))
    placed = []
    monkeypatch.setattr(cts.exchange, "place", lambda plan, note="": (placed.append((plan, note)), "Добре")[1])
    cts.open_trade("BTC", "short")
    plan, note = placed[0]
    atr = cts.prepared.s["atr1"][-1]
    assert plan.side == "short" and "ВНИМАНИЕ" in note
    assert plan.stop == risk.round_price(100.0 + 1.5 * atr, 5)
    assert plan.target == risk.round_price(100.0 - 3.0 * atr, 5)


def test_open_trade_proposes_again_after_a_price_move_then_gives_up(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [])
    monkeypatch.setattr(cts.exchange, "account_state", account(100.0))
    calls = []

    def moved(plan, note=""):
        calls.append(plan)
        raise exchange.PriceMoved(101.0)

    monkeypatch.setattr(cts.exchange, "place", moved)
    assert "твърде бързо" in cts.open_trade("BTC", "long")
    assert len(calls) == 2


def test_refusals_and_the_switch(cts, monkeypatch):
    monkeypatch.setattr(cts.signals, "latest", lambda p: [])
    monkeypatch.setattr(cts.exchange, "account_state",
                        lambda network: (risk.AccountState(1000.0, {"BTC": {}}),
                                         {"BTC": {"mid": 100.0, "sz_decimals": 5, "max_leverage": 40}}))
    assert "Вече имате позиция в Биткойн" in cts.open_trade("BTC", "long")
    assert "лонг" in cts.open_trade("BTC", "нагоре-надолу")
    cts.pause_trading()
    assert "спряна" in cts.open_trade("BTC", "long")
    cts.resume_trading()


def test_close_all(cts, monkeypatch):
    closed = []
    monkeypatch.setattr(cts.exchange, "close", lambda coins, network, reason="": (closed.append(coins), "Затворих: x")[1])
    assert cts.close_trade("всички") == "Затворих: x"
    assert closed == [["BTC", "ETH", "SOL"]]
    cts.close_trade("етериума")
    assert closed[-1] == ["ETH"]


def test_connect_opens_the_key_dialog(cts, monkeypatch):
    shown = []
    monkeypatch.setattr(trading, "show_key_dialog", shown.append)
    assert "app.hyperliquid-testnet.xyz" in cts.connect_hyperliquid()
    assert "ИСТИНСКИ" in cts.connect_hyperliquid("истински пари")
    assert shown == ["testnet", "mainnet"]


def test_mainnet_needs_the_warning_dialog(cts, monkeypatch):
    monkeypatch.setattr(confirm, "handler", lambda *args: False)
    assert "тестовата мрежа" in cts.switch_trading_network("истински пари")
    assert cts.settings.network() == "testnet"
    monkeypatch.setattr(confirm, "handler", lambda *args: True)
    assert cts.switch_trading_network("mainnet").startswith("Минах на истински пари")
    assert cts.settings.network() == "mainnet"
    cts.switch_trading_network("тестовата мрежа")
    assert cts.settings.network() == "testnet"


def test_texts_for_the_record_and_the_table(cts):
    texts = cts.texts
    assert "още няма приключили сигнали" in texts.record_text(
        {"days": 7, "n": 0, "wins": 0, "win_rate": 0, "avg_r": 0, "open": 2, "by_strategy": {}})
    summary = {"days": 7, "n": 4, "wins": 3, "win_rate": 0.75, "avg_r": 0.8, "open": 0,
               "by_strategy": {"breakout": {"n": 4, "wins": 3, "r": 3.2}}}
    assert texts.record_text(summary) == ("За последните 7 дни: 4 приключили сигнала, 3 на печалба (75 %), средно "
                                          "+0.80 пъти риска. По стратегии: пробив 3 от 4.")
    weak = {"trades": 40, "win_rate": 0.3, "win_low": 0.2, "win_high": 0.45, "avg_r": -0.1, "profit_factor": 0.8,
            "max_drawdown_r": 9.0}
    report = {"time": 0, "coins": {"BTC": {"pullback": weak, "breakout": weak, "reversal": weak,
                                           "range": {"hits": 70, "total": 100}, "from": 0, "to": 0}}}
    table = texts.strategy_table(report)
    assert "не мина" in table and "нямам предимство" in table
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_skills.py -q`
Expected: FAIL — `KeyError: 'skills.crypto_trading_skills'`

- [ ] **Step 3: Write `orion/trading/texts.py`**

```python
"""
Everything Orion says about forecasts, strategies, the record, the account and fills — in Bulgarian, built
only from numbers the code computed (the language model just reads it out).
"""
from datetime import datetime

from ..markets import _fmt
from . import NAMES, backtest
from .signals import LABELS

SIDE = {"long": "ЛОНГ", "short": "ШОРТ"}
TREND = {1: "нагоре", -1: "надолу", 0: "без ясна посока"}
NOT_ADVICE = "Това е вероятност, не гаранция, и не е инвестиционен съвет."
NO_DATA = ("Няма връзка с пазарните данни на Hyperliquid в момента, затова не давам прогноза — не искам да Ви "
           "казвам стари числа. Опитайте пак след малко.")
NO_REPORT = ("Проверката върху историята още се изчислява (първия път отнема няколко минути), затова още не "
             "казвам колко често печели тази стратегия.")
CONNECT_STEPS = {
    "testnet": ("Отворих прозореца за ключа. Стъпките: първо отворете app.hyperliquid-testnet.xyz и свържете Trust "
                "Wallet; после страницата API — натиснете Generate и одобрете в Trust Wallet; накрая поставете "
                "адреса на портфейла и API ключа в прозореца. Никога не поставяйте думите за възстановяване."),
    "mainnet": ("Отворих прозореца за ключа за ИСТИНСКИ пари. Стъпките: отворете app.hyperliquid.xyz и свържете "
                "Trust Wallet; страницата API — Generate и одобрете в Trust Wallet; поставете адреса и API ключа в "
                "прозореца. Този ключ може само да търгува — не може да тегли пари. Никога не поставяйте думите "
                "за възстановяване."),
}
MAINNET_WARNING = ("От сега сделките ще са с ИСТИНСКИ пари. Всяка сделка пак чака Вашето „Одобри“ и лимитите "
                   "остават (2 % риск на сделка, до 10x, до 6 % загуба на ден), но загубите ще са истински. "
                   "Препоръчвам поне 1–2 седмици в тестовата мрежа преди това.")


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
```

- [ ] **Step 4: Write `skills/crypto_trading_skills.py`**

```python
"""
Крипто прогнози и търговия: биткойн, етериум и солана на Hyperliquid. Числата идват от кода — три
стратегии с честна проверка върху историята; всяка истинска сделка чака „Одобри“ от сър.
"""
from datetime import datetime

from orion import confirm, markets, orion_tool, trading
from orion.trading import (COINS, NAMES, backtest, coin_from_text, exchange, journal, market, risk, settings,
                           signals, texts)

# The forecast chart — app.py shows it in the journal after crypto_forecast.
last_chart: dict | None = None
REFUSALS = (risk.RiskError, exchange.TradingError, ValueError)
MAINNET_WORDS = ("mainnet", "истински", "истински пари", "реални", "реални пари", "истинска", "истинската мрежа",
                 "за истински пари")


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


@orion_tool
def trading_positions() -> str:
    """Отворените позиции в Hyperliquid сега: монета, лонг или шорт, размер и печалба или загуба."""
    network = settings.network()
    try:
        state, _ = exchange.account_state(network)
    except REFUSALS as e:
        return str(e)
    return texts.positions_text(state, network)


@orion_tool
def trading_account() -> str:
    """Сметката в Hyperliquid: колко пари има, днешната загуба спрямо лимита и рискът на сделка."""
    network = settings.network()
    try:
        state, _ = exchange.account_state(network)
    except REFUSALS as e:
        return str(e)
    return texts.account_text(state, network, settings.limits())


@orion_tool
def open_trade(coin: str, side: str) -> str:
    """Отваря истинска сделка — лонг или шорт — на биткойн, етериум или солана в Hyperliquid. Орион
    изчислява размера по лимитите и показва прозорец „Одобри“; без него нищо не се отваря.

    Args:
        coin: Монетата — "биткойн", "етериум" или "солана".
        side: "лонг" (за покачване) или "шорт" (за спадане).
    """
    try:
        c, direction = coin_from_text(coin), _side(side)
    except ValueError as e:
        return str(e)
    if not settings.enabled():
        return "Търговията е спряна. Кажете „пусни търговията“, за да я включите."
    network = settings.network()
    try:
        p = market.live(c)
    except OSError:
        return texts.NO_DATA
    signal = next((s for s in signals.latest(p) if s.side == direction), None)
    if signal:  # the distances of the signal — re-anchored to the price of the network sir trades on
        stop_gap, target_gap = signal.entry - signal.stop, signal.target - signal.entry
        note, strategy = f"Сигнал: {signals.LABELS[signal.strategy]}, сила {signal.strength} от 5.", signal.strategy
    else:
        atr = p.s["atr1"][-1] or p.h1.c[-1] * 0.01
        sign = 1 if direction == "long" else -1
        stop_gap, target_gap = sign * 1.5 * atr, sign * 3.0 * atr
        note, strategy = "ВНИМАНИЕ: в момента няма сигнал в тази посока — влизате без сигнал.", "без сигнал"
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
def close_trade(coin: str) -> str:
    """Затваря отворена позиция в Hyperliquid (или всички) — след „Одобри“ от сър.

    Args:
        coin: Монетата ("биткойн", "етериум", "солана") или "всички".
    """
    try:
        coins = list(COINS) if coin.strip().lower() in ("всички", "всичко", "all") else [coin_from_text(coin)]
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
    """Спира търговията: Орион не отваря нови сделки, докато сър не каже „пусни търговията“."""
    settings.set_enabled(False)
    return "Спрях търговията — няма да отварям нови сделки. Отворените позиции остават със стоповете си."


@orion_tool
def resume_trading() -> str:
    """Пуска търговията отново (всяка сделка пак чака „Одобри“)."""
    settings.set_enabled(True)
    return "Пуснах търговията отново — всяка сделка пак чака Вашето „Одобри“."


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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_skills.py -q`
Expected: PASS

- [ ] **Step 6: Run every test so far**

Run: `python -m pytest -q`
Expected: PASS (the earlier suites still pass — `test_app_live.py` loads all skills, including the new file)

- [ ] **Step 7: Commit**

```bash
git add orion/trading/texts.py skills/crypto_trading_skills.py tests/test_trading_skills.py
git commit -m "Trading skills: forecasts, signals, strategy report, record, positions, open/close with approval"
```

---
### Task 11: Wiring — reflexes, router words, intent nudge, persona, test-mode asks

**Files:**
- Modify: `orion/reflexes.py` (new regexes + `_trading_command`, one call in `respond()`)
- Modify: `orion/router.py` (`GROUPS`: one new entry)
- Modify: `orion/brain.py` (`INTENT_TOOLS`: one entry at the top; `READ_ONLY_TOOLS`: six names)
- Modify: `config.py` (persona: one line after the markets line)
- Modify: `orion/self_test_cases.py` (`SKILL_CASES` and `ASKS`)
- Test: `tests/test_trading_reflexes.py`

**Interfaces:**
- Consumes: `trading.coins_in`, `exchange.last_open`, skill names from Task 10
- Produces: `reflexes._trading_command(plain: str) -> Reflex | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_reflexes.py`:

```python
import json

import pytest

from orion import brain, reflexes, router
from orion.trading import exchange


@pytest.mark.parametrize("text, tool, args", [
    ("Орион, отвори лонг на биткойн", "open_trade", {"coin": "биткойн", "side": "long"}),
    ("Отвори шорт на етериума", "open_trade", {"coin": "етериума", "side": "short"}),
    ("влез лонк в солана", "open_trade", {"coin": "солана", "side": "long"}),
    ("шорт на BTC", "open_trade", {"coin": "BTC", "side": "short"}),
    ("Затвори позицията на биткойна", "close_trade", {"coin": "биткойна"}),
    ("затвори етериума", "close_trade", {"coin": "етериума"}),
    ("Затвори всички позиции", "close_trade", {"coin": "всички"}),
    ("Спри търговията", "pause_trading", {}),
    ("Пусни търговията", "resume_trading", {}),
    ("Какви позиции имам?", "trading_positions", {}),
    ("Свържи Hyperliquid", "connect_hyperliquid", {"network": "testnet"}),
    ("свържи хайперликуид за истински пари", "connect_hyperliquid", {"network": "mainnet"}),
    ("Мини на истински пари", "switch_trading_network", {"network": "mainnet"}),
    ("Мини на тестовата мрежа", "switch_trading_network", {"network": "testnet"}),
])
def test_trading_commands_are_reflexes(text, tool, args):
    reflex = reflexes.respond(text)
    assert reflex is not None and reflex.tool == tool and reflex.arguments == args


@pytest.mark.parametrize("text", ["отвори Chrome", "затвори Steam", "какво мислиш за лонг на биткойн", "затвори доги"])
def test_other_phrases_are_not_trading(text):
    assert reflexes._trading_command(reflexes._plain(text)) is None


def test_close_everything_only_with_known_positions(monkeypatch):
    monkeypatch.setattr(exchange, "last_open", set())
    assert reflexes._trading_command("затвори всичко") is None
    monkeypatch.setattr(exchange, "last_open", {"BTC"})
    assert reflexes._trading_command("затвори всичко").arguments == {"coin": "всички"}


def test_the_trading_group_is_shown_only_when_relevant():
    assert "skills.crypto_trading_skills" not in router.excluded_modules("Какво ще прави солана?")
    assert "skills.crypto_trading_skills" not in router.excluded_modules("Колко пъти позна тази седмица?")
    assert "skills.crypto_trading_skills" in router.excluded_modules("Пусни радио Хоризонт")


def test_a_forecast_question_nudges_towards_crypto_forecast():
    name, arguments = brain.Brain._default_call("Какво ще прави биткойнът днес?")
    assert name == "crypto_forecast" and json.loads(arguments) == {"coin": "Какво ще прави биткойнът днес?"}
    assert brain.Brain._default_call("Направи ми анализ на златото")[0] != "crypto_forecast"
    assert {"crypto_forecast", "trading_positions"} <= brain.READ_ONLY_TOOLS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_reflexes.py -q`
Expected: FAIL — `AttributeError: module 'orion.reflexes' has no attribute '_trading_command'` (and the parametrized cases return other reflexes or None)

- [ ] **Step 3: Add the reflexes**

In `orion/reflexes.py`, directly above `def _everyday(plain: str) -> Reflex | None:` add:

```python
# Trading (orion/trading) — before „отвори …“ (programs) and „затвори …“ (windows): „отвори лонг на биткойн“.
_SIDE_WORDS = r"(?P<side>лонг|лонк|long|шорт|шорд|short)"
_TRADE_OPEN_RE = re.compile(
    rf"(?:(?:отвори|отворете|отвориш|влез|влезте|пусни|направи)(?: (?:ми|ни))?(?: (?:една|нова|един|нов))? )?"
    rf"{_SIDE_WORDS}(?: (?:позиция|сделка))?(?: (?:на|в|за|с|по))? (?P<coin>[^?!.]+)", re.IGNORECASE)
_TRADE_CLOSE_RE = re.compile(
    r"(?:затвори|затворете|затвориш|излез от|излезте от)(?: ми)?(?: (?:позицията|позициите|сделката|сделките))?"
    r"(?: (?:на|в|по|с))? (?P<coin>[^?!.]+)", re.IGNORECASE)
_TRADE_ALL_RE = re.compile(
    r"(?:затвори|затворете)(?: ми)? (?:(?:всички|всичките) (?:позиции|сделки)|позициите|сделките)", re.IGNORECASE)
_TRADE_PAUSE_RE = re.compile(r"спри (?:търговията|да търгуваш|трейдинга|трейдването)", re.IGNORECASE)
_TRADE_RESUME_RE = re.compile(r"(?:пусни|включи|продължи|започни) (?:търговията|да търгуваш|трейдинга)",
                              re.IGNORECASE)
_TRADE_POSITIONS_RE = re.compile(
    r"(?:какви|кои) (?:позиции|сделки) (?:имам|са отворени|има)|(?:покажи|кажи|прочети)(?: ми)? "
    r"(?:позициите|сделките)(?: ми)?|(?:отворените|отворени) (?:позиции|сделки)", re.IGNORECASE)
_TRADE_CONNECT_RE = re.compile(
    r"свържи(?: се)?(?: с)? (?:hyperliquid|хайперликуид|хиперликуид|хайпър ликуид|хипер ликуид)"
    r"(?: (?P<net>за истински пари|истинск\w*|реалн\w*))?", re.IGNORECASE)
_TRADE_NETWORK_RE = re.compile(
    r"мини на (?P<net>истински пари|реални пари|тестовата мрежа|тестнет|тест мрежата)", re.IGNORECASE)


def _trading_command(plain: str) -> Reflex | None:
    """Trading commands: always the same skill, never the model's guess (it has bluffed actions before)."""
    from .trading import coins_in, exchange
    for pattern, tool in ((_TRADE_PAUSE_RE, "pause_trading"), (_TRADE_RESUME_RE, "resume_trading"),
                          (_TRADE_POSITIONS_RE, "trading_positions")):
        if pattern.fullmatch(plain):
            return Reflex(tool=tool, arguments={})
    match = _TRADE_CONNECT_RE.fullmatch(plain)
    if match:
        return Reflex(tool="connect_hyperliquid", arguments={"network": "mainnet" if match["net"] else "testnet"})
    match = _TRADE_NETWORK_RE.fullmatch(plain)
    if match:
        network = "testnet" if "тест" in match["net"].lower() else "mainnet"
        return Reflex(tool="switch_trading_network", arguments={"network": network})
    # „Затвори всичко“ may mean the windows — it is about trades only while positions are open.
    if _TRADE_ALL_RE.fullmatch(plain) or (plain.lower() == "затвори всичко" and exchange.last_open):
        return Reflex(tool="close_trade", arguments={"coin": "всички"})
    match = _TRADE_OPEN_RE.fullmatch(plain)
    if match and coins_in(match["coin"]):
        side = "long" if match["side"].lower() in ("лонг", "лонк", "long") else "short"
        return Reflex(tool="open_trade", arguments={"coin": match["coin"].strip(), "side": side})
    match = _TRADE_CLOSE_RE.fullmatch(plain)
    if match and coins_in(match["coin"]):
        return Reflex(tool="close_trade", arguments={"coin": match["coin"].strip()})
    return None
```

In `respond()`, find:

```python
    for pattern, action in ((_TEST_OFF_RE, "test_off"), (_TEST_REPORT_RE, "test_report"), (_TEST_ON_RE, "test_on")):
        if pattern.fullmatch(plain):
            return Reflex(action=action)
```

and add right after it:

```python
    trade = _trading_command(plain)
    if trade:
        return trade
```

- [ ] **Step 4: Add the router group**

In `orion/router.py`, find the end of the `"skills.trading_skills"` entry:

```python
        r"победител|губещ|растат|падат|акции|в евро|в лева|биткойн|крипт|етер", re.IGNORECASE),
```

and add right after it:

```python
    "skills.crypto_trading_skills": re.compile(
        r"лонг|лонк|шорт|long|short|позици|сделк|трейд|търгув|ливъридж|стоп|хайперликуид|хиперликуид|hyperliquid|"
        r"прогноз|сигнал|позна|стратеги|биткойн|биткоин|bitcoin|btc|етериум|етер|ethereum|eth|солан|solana|"
        r"тестовата мрежа|истински пари", re.IGNORECASE),
```

- [ ] **Step 5: Add the intent nudge and the read-only names**

In `orion/brain.py`, find `INTENT_TOOLS = [` and add as the FIRST entry of the list:

```python
    # Forecasts and trades of BTC/ETH/SOL — before the general market and search entries below.
    (re.compile(r"(?:прогноз|сигнал|какво ще (?:прави|направи)|накъде|лонг|шорт)\w*.*?"
                r"(?:биткойн|биткоин|bitcoin|btc|етериум|етер|ethereum|eth|солан|solana)|"
                r"(?:биткойн|биткоин|bitcoin|btc|етериум|етер|ethereum|eth|солан|solana)\w*.*?"
                r"(?:прогноз|сигнал|какво ще прави|накъде|лонг|шорт)", re.IGNORECASE),
     "crypto_forecast, crypto_signals, open_trade или close_trade", ("crypto_forecast", {"coin": USER_TEXT})),
```

In the same file, find:

```python
    "convert_currency", "convert_units",
}
```

and replace with:

```python
    "convert_currency", "convert_units",
    "crypto_forecast", "crypto_signals", "strategy_report", "forecast_record", "trading_positions", "trading_account",
}
```

- [ ] **Step 6: Add the persona line**

In `config.py`, find the line that starts with `- Пазари (акции, крипто, валути, злато, индекси):` and add this line right after it:

```
- Крипто прогнози и търговия (биткойн, етериум, солана в Hyperliquid): прогноза — crypto_forecast, всички сигнали — crypto_signals, колко добри са стратегиите — strategy_report, колко позна — forecast_record, позиции — trading_positions, сметка — trading_account, сделки — open_trade и close_trade (сър одобрява всяка в прозорец). Числата идват само от тези умения — никога не измисляш цена, процент или посока; казваш колко често сигналът е печелил и че е вероятност, не гаранция.
```

- [ ] **Step 7: Add the test-mode cases and asks**

In `orion/self_test_cases.py`, find:

```python
    C("portfolio_show", {}, r"(?i)биткойн|bitcoin|btc"), C("portfolio_remove", {"asset": "биткойн"}),
```

and add right after it:

```python
    C("strategy_report"), C("forecast_record", {"days": 7}, r"За последните"),
    C("crypto_forecast", {"coin": "биткойн"}, r"(?i)биткойн"), C("crypto_signals", {}, r"(?i)етериум"),
```

Find:

```python
    A("Кажи ми, когато биткойнът стигне 150 хиляди долара", ("set_price_alert",)),
```

and add right after it:

```python
    A("Какво ще прави биткойнът днес?", ("crypto_forecast", "crypto_signals")),
    A("Дай ми прогноза за солана", ("crypto_forecast",)),
    A("Има ли сигнали за крипто сега?", ("crypto_signals", "crypto_forecast")),
    A("Колко пъти позна тази седмица?", ("forecast_record",)),
    A("Колко добри са стратегиите ти за търговия?", ("strategy_report",)),
    A("Отвори шорт на етериум", ("open_trade",)),
    A("Затвори позицията на биткойна", ("close_trade",)),
    A("Какви позиции имам?", ("trading_positions", "trading_account")),
```

- [ ] **Step 8: Run the tests**

Run: `python -m pytest tests/test_trading_reflexes.py -q`
Expected: PASS

Run: `python -m pytest -q`
Expected: PASS (all suites)

- [ ] **Step 9: Commit**

```bash
git add orion/reflexes.py orion/router.py orion/brain.py config.py orion/self_test_cases.py tests/test_trading_reflexes.py
git commit -m "Trading wiring: command reflexes, router words, forecast nudge, persona, test-mode asks"
```

---

### Task 12: The background watch and the app wiring (incl. the secret guard)

**Files:**
- Create: `orion/trading/watcher.py`
- Modify: `app.py` (imports, `start()`, new `_trading_loop`, `_boot()`, `ask()`, chart after a skill, `HudApi.save_trading_key`)
- Test: `tests/test_trading_watcher.py`, `tests/test_app_trading.py`

**Interfaces:**
- Consumes: `market.live`, `signals.latest`, `journal.*`, `backtest.load/is_enabled/stale/refresh_async`, `settings.*`, `exchange.account_state/fills_since/last_open`, `data.assets/record_open_interest`, `texts.signal_alert/fill_text`
- Produces: `Watcher(say, hud, lock, clock=time.time)` with `run()`, `tick()`, `scan()`, `positions()`, `announce(text)`; hud calls `("addLog", "trading", text)` and `("setTrading", {"network", "positions": [{"coin", "side", "pnl_usd", "pnl_pct"}]} | None)`; `HudApi.save_trading_key(network, address, key) -> {"ok": bool, "message": str}`; hud call `("showKeyDialog", {"network": ...})`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trading_watcher.py`:

```python
import threading
from datetime import datetime

import pytest

from orion.trading import backtest, data, exchange, journal, market, risk, settings, signals, watcher
from orion.trading.signals import Signal

GOOD = {"trades": 40, "win_rate": 0.5, "win_low": 0.35, "win_high": 0.65, "avg_r": 0.3, "profit_factor": 1.6,
        "max_drawdown_r": 5.0}
REPORT = {"time": 0, "coins": {"BTC": {"pullback": GOOD}}}


class Clock:
    def __init__(self, hour):
        self.now = datetime(2026, 10, 3, hour, 0).timestamp()

    def __call__(self):
        return self.now


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(market, "live", lambda coin, params=None: coin)
    found = {"BTC": [], "ETH": [], "SOL": []}
    monkeypatch.setattr(signals, "latest", lambda coin: found[coin])
    monkeypatch.setattr(backtest, "load", lambda: REPORT)
    monkeypatch.setattr(backtest, "stale", lambda: False)
    monkeypatch.setattr(data, "assets", lambda: {})
    monkeypatch.setattr(data, "record_open_interest", lambda found_: None)
    monkeypatch.setattr(exchange, "last_open", set())
    return found


def make(hour=10):
    said, hud = [], []
    w = watcher.Watcher(said.append, lambda fn, *args: hud.append((fn, args)), threading.Lock(), Clock(hour))
    return w, said, hud


def sig(time, strength=4, strategy="pullback"):
    return Signal("BTC", strategy, "long", time, 84000.0, 83000.0, 86000.0, strength, ["отскок в тренда"])


def test_a_strong_checked_signal_is_announced_once(world):
    w, said, hud = make()
    world["BTC"] = [sig(1)]
    w.scan()
    assert len(said) == 1 and "ЛОНГ на биткойн" in said[0]
    assert ("addLog", ("trading", said[0])) in hud
    w.scan()                                         # the same candle again
    world["BTC"] = [sig(2)]
    w.scan()                                         # a new candle, same coin and side, within 6 h
    assert len(said) == 1
    w.clock.now += 6 * 3600
    world["BTC"] = [sig(3)]
    w.scan()
    assert len(said) == 2


def test_weak_or_unchecked_signals_stay_quiet(world):
    w, said, hud = make()
    world["BTC"] = [sig(1, strength=3), sig(2, strategy="breakout")]
    w.scan()
    assert said == [] and not [h for h in hud if h[0] == "addLog"]
    assert journal.record(days=1)["open"] == 2       # still recorded for the honest record


def test_at_night_only_the_journal(world):
    w, said, hud = make(hour=2)
    world["BTC"] = [sig(1)]
    w.scan()
    assert said == [] and hud[0][0] == "addLog"


def test_positions_chip_fills_and_time_stop(world, monkeypatch):
    w, said, hud = make()
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    state = risk.AccountState(1000.0, {"BTC": {"side": "long", "size": 0.01, "entry": 84000.0, "pnl": 5.0,
                                               "liq": 0.0, "value": 500.0}})
    monkeypatch.setattr(exchange, "account_state", lambda network: (state, {}))
    fills = [{"coin": "ETH", "dir": "Close Short", "px": "1900", "closedPnl": "2", "time": 5},
             {"coin": "ETH", "dir": "Close Short", "px": "1901", "closedPnl": "3", "time": 6},
             {"coin": "BTC", "dir": "Open Long", "px": "84000", "closedPnl": "0", "time": 7}]
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [f for f in fills if f["time"] >= since])
    w.fills_from = 0
    plan = risk.OrderPlan("BTC", "long", 0.01, 84000.0, 83000.0, 86000.0, 2, 840.0, 420.0, 10.0, 20.0, 0.0, 0.8,
                          "testnet")
    monkeypatch.setattr(journal, "_now", lambda: int(w.clock.now * 1000))
    journal.add_trade(plan, "пробив")
    w.clock.now += 49 * 3600
    w.positions()
    assert ("setTrading", ({"network": "testnet", "positions": [
        {"coin": "BTC", "side": "long", "pnl_usd": 5.0, "pnl_pct": 1.0}]},)) in hud
    assert [s for s in said if "Етериум" in s] == ["Сър, позицията в Етериум се затвори на 1 901 — +5.00 долара."]
    assert sum("48 часа" in s for s in said) == 1
    w.positions()
    assert sum("48 часа" in s for s in said) == 1     # told once
    assert sum("Етериум" in s for s in said) == 1     # fills are not repeated


def test_no_key_hides_the_chip(world):
    w, said, hud = make()
    w.positions()
    assert hud == [("setTrading", (None,))]


def test_tick_runs_each_job_on_its_own_schedule(world, monkeypatch):
    w, said, hud = make()
    calls = []
    monkeypatch.setattr(w, "scan", lambda: calls.append("scan"))
    monkeypatch.setattr(w, "positions", lambda: calls.append("positions"))
    monkeypatch.setattr(journal, "resolve", lambda bars_for=None: calls.append("resolve"))
    w.tick()
    assert calls == ["scan", "positions", "resolve"]
    calls.clear()
    w.clock.now += 120
    w.tick()
    assert calls == []                               # no positions: every 5 minutes
    w.clock.now += 15 * 60
    w.tick()
    assert calls == ["scan", "positions"]
```

Create `tests/test_app_trading.py`:

```python
import queue
import threading

import app
from orion.trading import exchange, settings


def bare_app(said, hud_calls):
    orion = app.Orion.__new__(app.Orion)
    orion.hud = lambda fn, *args: hud_calls.append((fn, args))
    orion._pending_lock, orion._pending, orion.tasks = threading.Lock(), 0, queue.Queue()
    orion.say = said.append
    return orion


def test_a_key_typed_in_the_chat_is_never_processed(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "s.json")
    said, hud_calls = [], []
    orion = bare_app(said, hud_calls)
    orion.ask("0x" + "ab" * 32)
    orion.ask(" ".join(["abandon"] * 11 + ["about"]))
    assert orion.tasks.empty()
    assert hud_calls[0] == ("showKeyDialog", ({"network": "testnet"},))
    assert "таен ключ" in said[0] and "ab" * 32 not in said[0]
    orion.ask("Колко е часът?")
    assert orion.tasks.get_nowait() == ("ask", "Колко е часът?", "text")


def test_save_trading_key_reports_the_result(monkeypatch):
    said = []
    orion = bare_app(said, [])
    api = app.HudApi(orion)
    result = api.save_trading_key("testnet", "0x123", "k" * 64)
    assert result["ok"] is False and "Адресът" in result["message"]
    monkeypatch.setattr(settings, "save_account", lambda network, address, key: "Запазих API ключа.")
    monkeypatch.setattr(exchange, "check_connection", lambda network: "Свързах се.")
    result = api.save_trading_key("testnet", "0x" + "a" * 40, "b" * 64)
    assert result == {"ok": True, "message": "Запазих API ключа. Свързах се."}
    assert said == ["Запазих API ключа. Свързах се."]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trading_watcher.py tests/test_app_trading.py -q`
Expected: FAIL — `ImportError: cannot import name 'watcher'`; `AttributeError: 'HudApi' object has no attribute 'save_trading_key'`

- [ ] **Step 3: Write `orion/trading/watcher.py`**

```python
"""
The background watch (own thread, started by app.py). Every 15 minutes it checks the three coins: each
new signal goes into the journal, and a strong one (strength ≥ 4, from a strategy that passed the honest
check) is announced — by voice 08:00–23:00, otherwise only in the journal. With a key connected it checks
the account (every minute while positions are open, else every 5): the top-bar chip, closed trades, and
the 48-hour time stop (announced; sir closes it with one command and the approval dialog). It holds test
mode's sandbox lock while it works, so it never touches the sandbox's temporary files.
"""
import time
from datetime import datetime

from . import COINS, NAMES, backtest, data, exchange, journal, market, settings, signals, texts

SCAN_EVERY = 15 * 60
RESOLVE_EVERY = 60 * 60
REFRESH_RETRY = 30 * 60
REPEAT_HOURS = 6


class Watcher:
    def __init__(self, say, hud, lock, clock=time.time):
        self.say, self.hud, self.lock, self.clock = say, hud, lock, clock
        self.last_scan = self.last_positions = self.last_resolve = self.last_refresh = -1e18
        self.announced: dict[tuple[str, str], float] = {}
        self.fills_from = int(clock() * 1000)
        self.time_stop_told: set[str] = set()

    def run(self) -> None:
        while True:
            self.tick()
            time.sleep(5)

    def _safe(self, job) -> None:
        try:
            job()
        except Exception as e:  # noqa: BLE001 — the watch must never stop Orion
            print(f"[Trading] {getattr(job, '__name__', 'job')}: {type(e).__name__}: {e}")

    def tick(self) -> None:
        now = self.clock()
        with self.lock:
            if now - self.last_scan >= SCAN_EVERY:
                self.last_scan = now
                self._safe(self.scan)
            if now - self.last_positions >= (60 if exchange.last_open else 300):
                self.last_positions = now
                self._safe(self.positions)
            if now - self.last_resolve >= RESOLVE_EVERY:
                self.last_resolve = now
                self._safe(journal.resolve)
        if now - self.last_refresh >= REFRESH_RETRY and backtest.stale():
            self.last_refresh = now
            backtest.refresh_async(self.lock)

    # --- Signals ---------------------------------------------------------------------------------
    def scan(self) -> None:
        report = backtest.load()
        strength = settings.load()["announce_strength"]
        for coin in COINS:
            for s in signals.latest(market.live(coin)):
                if journal.add_signal(s, "watch") and self._worth(s, report, strength):
                    self.announce(texts.signal_alert(s, report))
        data.record_open_interest(data.assets())

    def _worth(self, s, report, strength: int) -> bool:
        if s.strength < strength or not backtest.is_enabled(report, s.coin, s.strategy):
            return False
        key = (s.coin, s.side)
        if self.clock() - self.announced.get(key, -1e18) < REPEAT_HOURS * 3600:
            return False
        self.announced[key] = self.clock()
        return True

    def announce(self, text: str) -> None:
        self.hud("addLog", "trading", text)
        start, end = settings.load()["voice_hours"]
        if start <= datetime.fromtimestamp(self.clock()).hour < end:
            self.say(text)

    # --- The account ------------------------------------------------------------------------------
    def positions(self) -> None:
        network = settings.network()
        if not settings.account(network):
            self.hud("setTrading", None)
            return
        state, _ = exchange.account_state(network)
        self.hud("setTrading", {"network": network, "positions": [
            {"coin": coin, "side": p["side"], "pnl_usd": round(p["pnl"], 2),
             "pnl_pct": round(p["pnl"] / p["value"] * 100, 2) if p["value"] else 0.0}
            for coin, p in state.positions.items()]})
        closed: dict[str, list[float]] = {}  # coin -> [last price, P/L] — a stop filled in parts is told once
        for fill in exchange.fills_since(network, self.fills_from):
            self.fills_from = max(self.fills_from, int(fill["time"]) + 1)
            if str(fill.get("dir", "")).startswith("Close"):
                entry = closed.setdefault(fill["coin"], [0.0, 0.0])
                entry[0] = float(fill["px"])
                entry[1] += float(fill.get("closedPnl") or 0)
        for coin, (price, pnl) in closed.items():
            self.announce(texts.fill_text({"coin": coin, "px": price, "closedPnl": pnl}))
            journal.close_trade(coin, price, pnl)
        now_ms = self.clock() * 1000
        for coin in state.positions:
            opened = journal.open_trade_time(coin)
            if opened and coin not in self.time_stop_told and now_ms - opened >= signals.TIME_STOP_HOURS * data.HOUR:
                self.time_stop_told.add(coin)
                name = NAMES.get(coin, coin).lower()
                self.announce(f"Сър, сделката в {name} е отворена от 48 часа — времето ѝ изтече. Кажете "
                              f"„затвори {name}“ и ще я затворя след Вашето одобрение.")
```

- [ ] **Step 4: Wire it into `app.py`**

Find:

```python
from orion import alerts, apps, confirm, games, google, live, reels, reflexes, self_test, speech, telemetry, vision  # noqa: E402
```

and add right after it:

```python
from orion import trading  # noqa: E402
from orion.trading import backtest as trading_backtest  # noqa: E402
from orion.trading import exchange as trading_exchange  # noqa: E402
from orion.trading import settings as trading_settings  # noqa: E402
from orion.trading import watcher as trading_watcher  # noqa: E402
```

In `start()`, find:

```python
            threading.Thread(target=self._reminder_loop, daemon=True, name="reminders").start()
```

and add right after it:

```python
            threading.Thread(target=self._trading_loop, daemon=True, name="trading").start()
```

Find `    def _reminder_loop(self) -> None:` and add this method directly ABOVE the `# --- Reminders` comment line that precedes it:

```python
    # --- Trading (orion/trading) -----------------------------------------------------------------
    def _trading_loop(self) -> None:
        """The trading watch — signals, positions, fills — after the greeting, in its own thread."""
        self.greeted.wait()
        trading_watcher.Watcher(say=self.say, hud=self.hud, lock=self_test.sandbox_lock).run()

```

In `_boot()`, find:

```python
        confirm.handler = self.request_confirmation  # emails, deleting — only with a button press from sir
```

and add right after it:

```python
        # Trading: the key dialog, and the backtest report is written only outside test mode's sandbox.
        trading.show_key_dialog = lambda network: self.hud("showKeyDialog", {"network": network})
        trading_backtest.save_lock = self_test.sandbox_lock
```

Replace `ask()`:

```python
    def ask(self, text: str, source: str = "text") -> None:
        text = (text or "").strip()
        if text:
            self._submit("ask", text, source)
```

with:

```python
    def ask(self, text: str, source: str = "text") -> None:
        text = (text or "").strip()
        if text and trading.looks_secret(text):
            # A private key or a recovery phrase must never reach the model, the journal or the log.
            self.hud("showKeyDialog", {"network": trading_settings.network()})
            self.say("Сър, това прилича на таен ключ или на думите за възстановяване на портфейл. Не ги пишете в "
                     "чата — не съм ги запазил никъде. Ако е API ключът на Hyperliquid, поставете го в прозореца, "
                     "който отворих.")
            return
        if text:
            self._submit("ask", text, source)
```

Find:

```python
        if ok and name in ("analyze_market", "analyze_price_file"):
            chart = getattr(skills.get("skills.market_skills"), "last_chart", None)
```

and replace with:

```python
        charts = {"analyze_market": "skills.market_skills", "analyze_price_file": "skills.market_skills",
                  "crypto_forecast": "skills.crypto_trading_skills"}
        if ok and name in charts:
            chart = getattr(skills.get(charts[name]), "last_chart", None)
```

In `class HudApi`, find:

```python
    def send_text(self, text: str):
        self._app.ask(text, "text")
```

and add right after it:

```python
    def save_trading_key(self, network: str, address: str, key: str):
        """The key dialog — never the chat, so the key reaches neither the journal nor the model."""
        try:
            message = trading_settings.save_account(network, address, key)
        except ValueError as e:
            return {"ok": False, "message": str(e)}
        try:
            message += " " + trading_exchange.check_connection(network)
        except Exception as e:  # noqa: BLE001 — the key is saved; the check can be repeated
            message += f" Не успях да проверя връзката: {e}"
        self._app.say(message)
        return {"ok": True, "message": message}
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_trading_watcher.py tests/test_app_trading.py -q`
Expected: PASS

Run: `python -m pytest -q`
Expected: PASS (all suites)

- [ ] **Step 6: Commit**

```bash
git add orion/trading/watcher.py app.py tests/test_trading_watcher.py tests/test_app_trading.py
git commit -m "Trading watch thread, key dialog hook, forecast chart, secret guard for the chat"
```

---
### Task 13: The practice account and the strategy lab

**Files:**
- Create: `orion/trading/practice.py`, `orion/trading/lab.py`
- Test: `tests/test_trading_practice.py`

**Interfaces:**
- Consumes: `market.live/history`, `signals.latest/signals_at/with_params/load_params/save_params/LABELS/STRATEGIES/WARMUP/TIME_STOP_HOURS`, `backtest.exit_walk/funding_cost/result_r/simulate/stats/SPLIT/Stats`, `risk.size_for`, `settings.limits/account`, `exchange.testnet_check`, `journal.add_signal`
- Produces:
  - `practice.PRACTICE`, `START = 10_000.0`, `load() -> dict`, `save(state)`, `open_signals(state, found, variant, limits) -> int`, `settle(state, bars_by_coin, funding_by_coin) -> list[dict]`, `by_strategy(state, variant="current") -> dict`, `@dataclass Round(balance, start, opened, closed, by_strategy, lab_note="", testnet_note="")` with `.summary() -> str`, `run(log=print) -> Round`
  - `lab.LAB`, `GRIDS`, `TRIAL_TRADES = 20`, `MARGIN = 0.10`, `SEARCH_EVERY_DAYS = 7`, `load()`, `save(state)`, `candidates() -> dict[str, dict]`, `variants(strategy, current) -> list[dict]`, `better(new_r, old_r) -> bool`, `search(strategy, markets_by_coin) -> tuple[dict, Stats, Stats] | None`, `step(practice_state, log=print, markets_by_coin=None) -> str`
  - Practice trade dict: the `Signal` fields + `variant` (`"current" | "candidate"`), `size`, and after settling `status` (`"closed" | "expired"`), `exit`, `exit_time`, `why`, `r`, `pnl`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_practice.py`:

```python
import copy

import pytest

from orion.trading import backtest, data, exchange, journal, lab, market, practice, settings, signals
from orion.trading.backtest import Stats
from orion.trading.data import HOUR, Bars
from orion.trading.risk import Limits
from orion.trading.signals import Signal
from test_trading_signals import random_walk


@pytest.fixture(autouse=True)
def temp_files(monkeypatch, tmp_path):
    monkeypatch.setattr(practice, "PRACTICE", tmp_path / "practice.json")
    monkeypatch.setattr(lab, "LAB", tmp_path / "lab.json")
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(signals, "PARAMS_FILE", tmp_path / "params.json")


def sig(time=10 * HOUR, strategy="pullback"):
    return Signal("BTC", strategy, "long", time, 100.0, 99.0, 102.0, 4, ["отскок в тренда"])


def candles(rows, start=10 * HOUR):
    bars = Bars(HOUR)
    for k, (o, h, l, c) in enumerate(rows):
        bars.add(start + k * HOUR, o, h, l, c, 1.0)
    return bars


def test_open_signals_sizes_like_a_real_trade_and_does_not_repeat():
    state = practice.load()
    assert practice.open_signals(state, [sig()], "current", Limits()) == 1
    assert state["open"][0]["size"] == pytest.approx(200.0)     # 2 % of 10 000 $ over a 1 $ stop
    assert practice.open_signals(state, [sig()], "current", Limits()) == 0
    assert practice.open_signals(state, [sig()], "candidate", Limits()) == 1


def test_settle_books_the_result_and_expires_what_is_too_old():
    state = practice.load()
    practice.open_signals(state, [sig()], "current", Limits())
    state["open"].append({**sig(time=1 * HOUR, strategy="breakout").to_dict(), "variant": "current", "size": 1.0})
    bars = candles([(100.0, 100.5, 99.5, 100.2), (100.2, 102.3, 100.0, 102.0)])
    closed = practice.settle(state, {"BTC": bars}, {})
    assert len(closed) == 1 and closed[0]["why"] == "цел"
    paid = 2 * data.DEFAULT_FUNDING
    r = (0.02 - 0.0013 - paid) / 0.01
    assert state["balance"] == pytest.approx(10_000 + r * 200.0)
    assert state["open"] == []
    assert [t["status"] for t in state["closed"]] == ["closed", "expired"]
    assert practice.by_strategy(state) == {"pullback": {"n": 1, "wins": 1, "r": pytest.approx(r, abs=1e-3)}}


def fake_prepared():
    h1 = random_walk(1200)
    return signals.prepare("BTC", h1, data.resample(h1, 4 * HOUR), data.resample(h1, 24 * HOUR), [],
                           copy.deepcopy(signals.DEFAULTS))


def test_a_round_opens_settles_and_checks_the_testnet_once_a_day(monkeypatch):
    p = fake_prepared()
    monkeypatch.setattr(market, "live", lambda coin, params=None: p)
    monkeypatch.setattr(signals, "latest", lambda p_: [Signal("BTC", "pullback", "long", p.h1.end(len(p.h1) - 1),
                                                              p.h1.c[-1], p.h1.c[-1] * 0.99, p.h1.c[-1] * 1.02, 4, [])])
    monkeypatch.setattr(lab, "step", lambda state, log=print: "")
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    checks = []
    monkeypatch.setattr(exchange, "testnet_check", lambda: (checks.append(1), "Проверката мина.")[1])
    first = practice.run()
    assert first.opened == 1 and first.testnet_note == "Проверката мина." and first.balance == 10_000.0
    second = practice.run()
    assert second.opened == 0 and second.testnet_note == "" and checks == [1]
    assert practice.load()["open"][0]["variant"] == "current"
    assert "тренировъчната сметка е 10 000 $ (+0.0 %)" in first.summary()


def test_lab_variants_and_the_margin():
    current = signals.DEFAULTS
    assert len(lab.variants("pullback", current["pullback"])) == 23
    assert len(lab.variants("breakout", current["breakout"])) == 23
    assert len(lab.variants("reversal", current["reversal"])) == 17
    assert lab.better(0.3, 0.2) and not lab.better(0.21, 0.2) and lab.better(0.05, -0.1)


def closed(strategy, variant, r, n, since=0):
    return [{"strategy": strategy, "variant": variant, "status": "closed", "r": r, "time": since + k}
            for k in range(n)]


def test_gate_b_promotes_only_after_20_better_practice_trades(monkeypatch):
    promoted = []
    monkeypatch.setattr(signals, "save_params", lambda strategy, numbers, why: promoted.append((strategy, numbers)))
    monkeypatch.setattr(lab, "search", lambda strategy, markets: None)
    lab.save({"candidates": {"breakout": {"params": {"channel": 48}, "since": 0}}, "log": [], "searched": {}})
    state = {"closed": closed("breakout", "candidate", 0.5, 19) + closed("breakout", "current", 0.1, 20)}
    assert lab.step(state, markets_by_coin={}) == ""
    assert promoted == [] and "breakout" in lab.candidates()
    state["closed"] += closed("breakout", "candidate", 0.5, 1, since=100)
    note = lab.step(state, markets_by_coin={})
    assert "минаха и двете проверки" in note and promoted == [("breakout", {"channel": 48})]
    assert lab.candidates() == {}


def test_gate_b_rejects_a_variant_that_does_worse(monkeypatch):
    monkeypatch.setattr(signals, "save_params", lambda *args: pytest.fail("must not promote"))
    monkeypatch.setattr(lab, "search", lambda strategy, markets: None)
    lab.save({"candidates": {"pullback": {"params": {"fast": 13}, "since": 0}}, "log": [], "searched": {}})
    state = {"closed": closed("pullback", "candidate", 0.1, 20) + closed("pullback", "current", 0.3, 20)}
    assert "не издържа тренировката" in lab.step(state, markets_by_coin={})
    assert lab.candidates() == {}


def test_gate_a_starts_a_trial_and_waits_a_week_before_searching_again(monkeypatch):
    good = Stats(40, 0.5, 0.35, 0.65, 0.4, 1.8, 4.0)
    old = Stats(40, 0.45, 0.3, 0.6, 0.2, 1.3, 5.0)
    searched = []
    monkeypatch.setattr(lab, "search", lambda strategy, markets: (searched.append(strategy), ({"fast": 13}, good, old))[1])
    note = lab.step({"closed": []}, markets_by_coin={})
    assert "пробвам нови числа за „отскок в тренда“" in note
    assert lab.candidates() == {"pullback": {"fast": 13}}
    lab.step({"closed": []}, markets_by_coin={})
    lab.step({"closed": []}, markets_by_coin={})
    lab.step({"closed": []}, markets_by_coin={})
    assert searched == ["pullback", "breakout", "reversal"]          # then nothing until a week has passed


def test_search_on_real_candles_returns_a_variant_and_both_judgements():
    p = fake_prepared()
    numbers, new, old = lab.search("pullback", {"BTC": p})
    assert numbers in lab.variants("pullback", signals.load_params()["pullback"])
    assert isinstance(new, Stats) and isinstance(old, Stats)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_practice.py -q`
Expected: FAIL — `ImportError: cannot import name 'lab'`

- [ ] **Step 3: Write `orion/trading/lab.py`**

```python
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
```

- [ ] **Step 4: Write `orion/trading/practice.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_trading_practice.py -q`
Expected: PASS. (`test_a_round_opens…` uses the same Prepared for all three coins; only the BTC signal is opened because the fake `latest` always returns a BTC signal — the dedupe key is the signal's coin, so the second and third coins add nothing.)

- [ ] **Step 6: Commit**

```bash
git add orion/trading/practice.py orion/trading/lab.py tests/test_trading_practice.py
git commit -m "Trading practice account and strategy lab with two promotion gates"
```

---

### Task 14: Test mode practises trading every round

**Files:**
- Modify: `orion/self_test.py` (constant, `Report` fields/summary/markdown, `Sandbox._enter`, `_round`, new `_practice`, `_finish`)
- Test: `tests/test_self_test_trading.py`

**Interfaces:**
- Consumes: `practice.run(log) -> Round`, `Round.summary()`, `Round.by_strategy`, `exchange.blocked`
- Produces: `self_test.LEGACY_EVERY = 3`; `Report.trading: Round | None`, `Report.trading_error: str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_self_test_trading.py`:

```python
from types import SimpleNamespace

from orion import self_test
from orion.trading import exchange, practice


def test_the_sandbox_blocks_the_exchange():
    assert not exchange.blocked
    with self_test.Sandbox():
        assert exchange.blocked
    assert not exchange.blocked


def test_practice_every_round_the_old_checks_every_third(monkeypatch):
    tester = self_test.SelfTester(SimpleNamespace())
    calls = []
    monkeypatch.setattr(tester, "_practice", lambda report: calls.append(("practice", report.number)))
    monkeypatch.setattr(tester, "_check_skills", lambda report, store: calls.append(("skills", report.number)))
    monkeypatch.setattr(tester, "_check_understanding",
                        lambda report, store, invent: calls.append(("asks", report.number)))
    monkeypatch.setattr(tester, "_fix", lambda report, store: None)
    monkeypatch.setattr(tester, "_hud", lambda *args: None)
    monkeypatch.setattr(tester, "_load_store", lambda: {"asks": [], "skills": [], "no_case": []})
    monkeypatch.setattr(tester, "_save_store", lambda store: None)
    monkeypatch.setattr(tester, "_untested", lambda store: [])
    for number in range(1, 5):
        tester._round(self_test.Report(number))
    assert [c for c in calls if c[0] == "practice"] == [("practice", n) for n in range(1, 5)]
    assert [c for c in calls if c[0] == "asks"] == [("asks", 1), ("asks", 4)]


def test_the_report_tells_the_practice_result():
    report = self_test.Report(2)
    report.trading = practice.Round(10240.0, 10000.0, 1, [], {"pullback": {"n": 4, "wins": 3, "r": 2.0}},
                                    "пробвам нови числа за „пробив“ в тренировката", "")
    assert report.summary() == ("тренировъчната сметка е 10 240 $ (+2.4 %), 4 приключили сделки, 3 на печалба; "
                                "пробвам нови числа за „пробив“ в тренировката.")
    markdown = report.markdown()
    assert "## Търговия (тренировка)" in markdown and "- отскок в тренда: 3 от 4, средно +0.50R" in markdown
    failed = self_test.Report(3)
    failed.trading_error = "OSError: no route"
    assert "тренировката по търговия не мина" in failed.summary()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_self_test_trading.py -q`
Expected: FAIL — `exchange.blocked` stays False inside the sandbox; `_round` has no `_practice`; `Report` has no `trading`

- [ ] **Step 3: Change `orion/self_test.py`**

Find:

```python
SKILLS_EVERY = 3        # skills (network, files) — every 3 rounds; understanding — every round
```

and replace with:

```python
SKILLS_EVERY = 3        # skills (network, files) — every 3 rounds
LEGACY_EVERY = 3        # skills + understanding — every 3rd round; trading practice (the main exercise) — every round
```

In `class Report`, find:

```python
    untested: list[str] = field(default_factory=list)
    stopped: bool = False
```

and replace with:

```python
    untested: list[str] = field(default_factory=list)
    stopped: bool = False
    trading: object | None = None        # orion.trading.practice.Round
    trading_error: str = ""
```

In `Report.summary`, find:

```python
        parts = []
        if self.skills_total:
```

and replace with:

```python
        parts = []
        if self.trading:
            parts.append(self.trading.summary())
        elif self.trading_error:
            parts.append("тренировката по търговия не мина (няма пазарни данни)")
        if self.skills_total:
```

In `Report.markdown`, find:

```python
        lines += [self.summary(), ""]
```

and replace with:

```python
        lines += [self.summary(), ""]
        if self.trading:
            from .trading.signals import LABELS
            lines += ["## Търговия (тренировка)", ""]
            for strategy, b in self.trading.by_strategy.items():
                lines.append(f"- {LABELS.get(strategy, strategy)}: {b['wins']} от {b['n']}, "
                             f"средно {b['r'] / b['n']:+.2f}R")
            lines.append("")
```

In `Sandbox._enter`, find:

```python
        self._set(confirm, "handler", lambda *args, **kwargs: False)
```

and add right after it:

```python
        from .trading import exchange as trading_exchange
        self._set(trading_exchange, "blocked", True)  # skills under test never reach the exchange
```

Replace the start of `_round`:

```python
    def _round(self, report: Report) -> None:
        store = self._load_store()
```

with:

```python
    def _round(self, report: Report) -> None:
        self._practice(report)  # trading practice — the main exercise, every round
        if report.number % LEGACY_EVERY != 1:
            return
        store = self._load_store()
```

Add this method right after `_round` (before the `# --- 1. Skills` comment):

```python
    def _practice(self, report: Report) -> None:
        """Trading practice: virtual trades on live prices, the strategy lab, the daily testnet check."""
        from .trading import practice
        self._wait_idle()
        self._progress("trading practice")
        self._hud("thought", "Самопроверка: тренирам търговия — виртуални сделки на истински цени.")
        try:
            report.trading = practice.run(log=self._log)
        except Exception as e:  # noqa: BLE001 — no market data now: the next round tries again
            report.trading_error = f"{type(e).__name__}: {e}"
            self._log(f"Тренировката по търговия не мина: {report.trading_error}")
```

In `_finish`, find:

```python
        news = report.count("сам", "одобрена", "неуспешна", "ядро") or report.skill_failures
```

and replace with:

```python
        news = report.count("сам", "одобрена", "неуспешна", "ядро") or report.skill_failures or \
            bool(report.trading and "нови числа" in report.trading.lab_note)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_self_test_trading.py -q`
Expected: PASS

Run: `python -m pytest -q`
Expected: PASS (all suites)

- [ ] **Step 5: Commit**

```bash
git add orion/self_test.py tests/test_self_test_trading.py
git commit -m "Test mode: trading practice every round, sandbox blocks the exchange, report"
```

---
### Task 15: The window — trading chip, key dialog, trade levels on the chart

**Files:**
- Create: `web/src/components/KeyDialog.jsx`, `web/src/components/Trading.test.jsx`
- Modify: `web/src/store.js`, `web/src/bridge.js`, `web/src/util.js`, `web/src/components/Jobs.jsx`, `web/src/components/Stage.jsx`, `web/src/components/Journal.jsx`, `web/src/engine/chart.js`, `web/src/styles.css`
- Build output: `ui/` (committed, as before)

**Interfaces:**
- Consumes: Python hud calls `setTrading(data | null)`, `showKeyDialog({network})`, `showChart(data)` with optional `entry/stop/target`; `pywebview.api.save_trading_key(network, address, key) -> {ok, message}`
- Produces: store keys `trading: string | null`, `keyDialog: {network} | null`; `KeyDialog` component

- [ ] **Step 1: Write the failing test**

Create `web/src/components/Trading.test.jsx`:

```jsx
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { hud } from '../bridge.js';
import { store } from '../store.js';
import { Jobs } from './Jobs.jsx';
import { KeyDialog } from './KeyDialog.jsx';

describe('trading in the window', () => {
  afterEach(() => {
    cleanup();
    store.set({ trading: null, keyDialog: null, test: null, reels: null, approval: null });
    delete window.pywebview;
  });

  it('the chip shows the network and the open positions', () => {
    hud.setTrading({ network: 'testnet', positions: [
      { coin: 'BTC', side: 'long', pnl_usd: 5, pnl_pct: 1.04 },
      { coin: 'ETH', side: 'short', pnl_usd: -2, pnl_pct: -0.4 },
    ] });
    const { container } = render(<Jobs />);
    expect(container.textContent).toContain('trading · TESTNET · BTC LONG +1.0% · ETH SHORT -0.4%');
  });

  it('no key or no positions on real money — no chip', () => {
    hud.setTrading(null);
    expect(store.get().trading).toBeNull();
    hud.setTrading({ network: 'mainnet', positions: [] });
    expect(store.get().trading).toBeNull();
  });

  it('the key goes to Python through its own call, never through the chat', async () => {
    const save = vi.fn().mockResolvedValue({ ok: true, message: 'ok' });
    const send = vi.fn();
    window.pywebview = { api: { save_trading_key: save, send_text: send } };
    hud.showKeyDialog({ network: 'testnet' });
    const { getByLabelText, getByText } = render(<KeyDialog />);
    expect(getByText('Hyperliquid · TESTNET')).toBeTruthy();
    fireEvent.change(getByLabelText(/Wallet address/), { target: { value: '0xabc' } });
    fireEvent.change(getByLabelText(/API wallet private key/), { target: { value: 'f'.repeat(64) } });
    fireEvent.click(getByText('Save key'));
    await waitFor(() => expect(store.get().keyDialog).toBeNull());
    expect(save).toHaveBeenCalledWith('testnet', '0xabc', 'f'.repeat(64));
    expect(send).not.toHaveBeenCalled();
  });

  it('a refused key keeps the dialog open with the reason', async () => {
    window.pywebview = { api: { save_trading_key: vi.fn().mockResolvedValue({ ok: false, message: 'Адресът трябва…' }) } };
    hud.showKeyDialog({ network: 'mainnet' });
    const { getByLabelText, getByText, findByRole } = render(<KeyDialog />);
    expect(getByText('Hyperliquid · REAL MONEY')).toBeTruthy();
    fireEvent.change(getByLabelText(/Wallet address/), { target: { value: '0x1' } });
    fireEvent.change(getByLabelText(/API wallet private key/), { target: { value: 'x' } });
    fireEvent.click(getByText('Save key'));
    expect((await findByRole('alert')).textContent).toContain('Адресът');
    expect(store.get().keyDialog).toEqual({ network: 'mainnet' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/Trading.test.jsx`
Expected: FAIL — `Failed to resolve import "./KeyDialog.jsx"`

- [ ] **Step 3: Store and bridge**

In `web/src/store.js`, find:

```js
  reels: null,                     // chip text while reels are being made
```

and add right after it:

```js
  trading: null,                   // chip text: the network and open positions (orion/trading/watcher.py)
  keyDialog: null,                 // { network } while the Hyperliquid key dialog is open
```

In `web/src/bridge.js`, find:

```js
  // Reels from YouTube: how far the background job has got.
  setReels({ active, text }) {
    store.set({ reels: active ? `reels · ${text || 'starting'}` : null });
  },
```

and add right after it:

```js

  // Trading (orion/trading/watcher.py): open positions with live P/L; TESTNET while on the test network.
  setTrading(data) {
    if (!data) {
      store.set({ trading: null });
      return;
    }
    const parts = data.positions.map((p) => `${p.coin} ${p.side.toUpperCase()} ${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct.toFixed(1)}%`);
    if (data.network === 'testnet') parts.unshift('TESTNET');
    store.set({ trading: parts.length ? `trading · ${parts.join(' · ')}` : null });
  },

  // The Hyperliquid API key — typed in its own dialog, never in the chat.
  showKeyDialog({ network }) {
    store.set({ keyDialog: { network } });
  },
```

In `web/src/util.js`, find:

```js
  claude: '▸ Claude', chart: '▸ market', test: '▸ test', reels: '▸ reels',
```

and replace with:

```js
  claude: '▸ Claude', chart: '▸ market', test: '▸ test', reels: '▸ reels', trading: '▸ trading',
```

- [ ] **Step 4: The chip**

Replace the body of `Jobs()` in `web/src/components/Jobs.jsx`:

```jsx
  const test = useStore((s) => s.test);
  const reels = useStore((s) => s.reels);
  const approval = useStore((s) => s.approval);
  const jobs = [test && ['test', test], reels && ['reels', reels], approval && ['approval', 'waiting for your approval']]
    .filter(Boolean);
```

with:

```jsx
  const test = useStore((s) => s.test);
  const reels = useStore((s) => s.reels);
  const trading = useStore((s) => s.trading);
  const approval = useStore((s) => s.approval);
  const jobs = [test && ['test', test], reels && ['reels', reels], trading && ['trading', trading],
    approval && ['approval', 'waiting for your approval']].filter(Boolean);
```

Update the comment above `export function Jobs()` to: `// Background work — test mode, reels, open trades, a proposal waiting for approval — always in sight.`

- [ ] **Step 5: The key dialog**

Create `web/src/components/KeyDialog.jsx`:

```jsx
import { useEffect, useRef, useState } from 'react';
import { store, useStore } from '../store.js';
import { api } from '../util.js';

// The Hyperliquid API key — typed here, never in the chat, so it reaches neither the journal nor the model.
export function KeyDialog() {
  const dialog = useStore((s) => s.keyDialog);
  const [address, setAddress] = useState('');
  const [key, setKey] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const first = useRef(null);
  useEffect(() => {
    if (!dialog) return;
    setAddress('');
    setKey('');
    setMessage('');
    first.current?.focus();
  }, [dialog]);
  if (!dialog) return null;
  const testnet = dialog.network !== 'mainnet';
  const close = () => store.set({ keyDialog: null });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const result = await api()?.save_trading_key(dialog.network, address.trim(), key.trim());
      if (result?.ok) close();
      else setMessage(result?.message || 'Could not save the key.');
    } finally {
      setBusy(false);
      setKey('');
    }
  };
  return (
    <form className="approval key-dialog" role="dialog" aria-labelledby="key-title" onSubmit={save}>
      <p className="approval-kind">{testnet ? 'Hyperliquid · TESTNET' : 'Hyperliquid · REAL MONEY'}</p>
      <h2 className="approval-title" id="key-title">Connect the API wallet</h2>
      <p className="key-warning">
        Никога не поставяйте думите за възстановяване (seed фразата). Тук — само API ключът от{' '}
        {testnet ? 'app.hyperliquid-testnet.xyz/API' : 'app.hyperliquid.xyz/API'}: той търгува, но не може да тегли.
      </p>
      <label className="key-field">
        Wallet address (Trust Wallet)
        <input ref={first} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="0x…"
          spellCheck={false} autoComplete="off" />
      </label>
      <label className="key-field">
        API wallet private key
        <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="0x…"
          spellCheck={false} autoComplete="off" />
      </label>
      {message && <p className="key-message" role="alert">{message}</p>}
      <div className="approval-actions">
        <button type="button" className="btn-reject" onClick={close}>Cancel</button>
        <button type="submit" className="btn-accept" disabled={busy || !address || !key}>Save key</button>
      </div>
    </form>
  );
}
```

In `web/src/components/Stage.jsx`, add to the imports:

```jsx
import { KeyDialog } from './KeyDialog.jsx';
```

and find:

```jsx
      <Approval />
```

and replace with:

```jsx
      <Approval />
      <KeyDialog />
```

In `web/src/styles.css`, find:

```css
.tele-chip--reels { color: var(--holo); border-color: var(--line-strong); }
```

and add right after it:

```css
.tele-chip--trading { color: var(--glow); border-color: var(--line-strong); }

/* The Hyperliquid key dialog — the approval card with two fields. */
.key-dialog { gap: 12px; }
.key-warning { margin: 0; color: #FFB3AC; font-size: 13.5px; line-height: 1.5; }
.key-field { display: flex; flex-direction: column; gap: 6px; color: var(--muted); font-size: 12.5px; }
.key-field input {
  font: 400 14px/1.4 var(--f-mono); color: var(--text); background: rgba(7, 18, 28, 0.85);
  border: 1px solid var(--line-strong); border-radius: 8px; padding: 9px 11px;
}
.key-field input:focus { outline: 2px solid var(--glow); outline-offset: 1px; }
.key-message { margin: 0; color: #FFB3AC; font-size: 13.5px; }
```

- [ ] **Step 6: Entry, stop and target on the chart**

In `web/src/engine/chart.js`, find:

```js
  price: '#2C9CCB', sma20: '#C2801F', sma50: '#9068D6',
```

and replace with:

```js
  price: '#2C9CCB', sma20: '#C2801F', sma50: '#9068D6',
  // A forecast's levels: the label carries the meaning; colour and dash pattern only help.
  entry: '#BCD9E8', stop: '#E06C5F', target: '#4FB286',
```

Find:

```js
  const values = [...data.close, ...data.sma20, ...data.sma50, data.support, data.resistance]
```

and replace with:

```js
  const values = [...data.close, ...data.sma20, ...data.sma50, data.support, data.resistance, data.entry, data.stop,
    data.target]
```

Find:

```js
  // A light wash under the price, then the lines.
```

and add directly ABOVE it:

```js
  // A forecast's entry, stop and target — dashed, labelled on the left (support/resistance are on the right).
  for (const [label, level, color, dash] of [['entry', data.entry, CHART.entry, [2, 3]],
    ['stop', data.stop, CHART.stop, [6, 4]], ['target', data.target, CHART.target, [10, 4]]]) {
    if (level == null) continue;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.setLineDash(dash);
    ctx.beginPath();
    ctx.moveTo(pad.l, y(level));
    ctx.lineTo(w - pad.r, y(level));
    ctx.stroke();
    ctx.setLineDash([]);
    const text = `${label} ${fmtPrice(level)}`;
    const tw = ctx.measureText(text).width;
    ctx.fillStyle = 'rgba(7,18,28,0.85)';
    ctx.fillRect(pad.l + 4, y(level) - 14, tw + 6, 12);
    ctx.fillStyle = color;
    ctx.textAlign = 'left';
    ctx.fillText(text, pad.l + 7, y(level) - 5);
  }

```

In `web/src/components/Journal.jsx`, find:

```jsx
          aria-label={`${data.name}: price ${fmtPrice(last)}, support ${fmtPrice(data.support)}, resistance ${fmtPrice(data.resistance)}`}
```

and replace with:

```jsx
          aria-label={`${data.name}: price ${fmtPrice(last)}, support ${fmtPrice(data.support)}, resistance ${fmtPrice(data.resistance)}${data.stop != null ? `, entry ${fmtPrice(data.entry)}, stop ${fmtPrice(data.stop)}, target ${fmtPrice(data.target)}` : ''}`}
```

- [ ] **Step 7: Run the web tests and build**

Run: `cd web && npm test`
Expected: PASS (all, including the existing Jobs, bridge and Eyes tests)

Run: `cd web && npm run build`
Expected: the build finishes and writes `ui/` (one classic script, relative paths — unchanged Vite config)

- [ ] **Step 8: Commit**

```bash
git add web/src ui
git commit -m "Window: trading chip, Hyperliquid key dialog, entry/stop/target on the forecast chart"
```

---

### Task 16: Real-data check, the real window, README, and the testnet run with sir

**Files:**
- Modify: `README.md` (new section)

- [ ] **Step 1: Every automated test**

Run: `python -m pytest -q`
Expected: PASS (all suites; none touches the network or sends an order)

Run: `cd web && npm test`
Expected: PASS

- [ ] **Step 2: The honest check on real data**

Check free space first (PowerShell): `Get-PSDrive C | Select-Object Free` — the cache is a few MB per coin.

Run: `python -m orion.trading.backtest`
Expected: the first run downloads ≈3.4 years of 1h candles per coin from Binance and Hyperliquid's funding history (a few minutes — funding pages are paced for Hyperliquid's rate limit), then prints the Bulgarian strategy table. Save the printed table — sir gets it word for word. Whatever it says (including „нито една стратегия не мина“) is reported as it is; do not tune anything by hand to make it look better.

- [ ] **Step 3: A live forecast from the code path**

Run:

```bash
python -c "import config; from orion.tools import registry; registry.load_skills(config.SKILLS_DIR); import sys; m = sys.modules['skills.crypto_trading_skills']; print(m.crypto_forecast('биткойн')); print(m.crypto_signals())"
```

Expected: Bulgarian text with the current BTC price from Hyperliquid, the trends, a signal or „Няма ясен сигнал“, and the not-advice line. The price must match app.hyperliquid.xyz within a few dollars.

- [ ] **Step 4: The real window**

Start Orion the usual way (the desktop shortcut, or `pythonw app.py`). In the chat type:
1. `Какво ще прави биткойнът?` → the answer reads the numbers from `crypto_forecast`; the journal shows the chart; with a signal the chart has `entry / stop / target` lines.
2. `Свържи Hyperliquid` → the key dialog opens (TESTNET); press Cancel.
3. Paste a fake key `0x` + 64 × `a` into the chat → Orion warns and opens the key dialog; the text appears in neither the journal nor `logs/orion.log` (check the log file).
4. `Какви позиции имам?` → „Hyperliquid не е свързан…“ (no key yet).
Take a screenshot of the chart and of the dialog for sir.

- [ ] **Step 5: README**

In `README.md`, add this section directly above `## Test mode — Orion checks and fixes itself`:

```markdown
## Crypto forecasts and trading (Hyperliquid)

Orion forecasts and trades **Bitcoin, Ethereum and Solana** on Hyperliquid — the exchange behind Trust
Wallet's "Perps" tab. Every number comes from code (`orion/trading/`); the language model only reads it out.

- „Какво ще прави биткойнът?“ / „Прогноза за солана“ — direction (or "no signal"), entry, stop, target,
  strength 1–5, and how often that strategy won in the honest check.
- „Сигнали“ — all three coins. „Колко добри са стратегиите?“ — the check, per strategy and coin.
  „Колко позна тази седмица?“ — the real outcomes of Orion's own signals.
- „Отвори лонг на биткойн“, „Затвори етериума“, „Затвори всички позиции“ — every open and close shows an
  approval dialog with every number; nothing happens without „Одобри“.
- „Спри търговията“ / „Пусни търговията“, „Мини на истински пари“ / „Мини на тестовата мрежа“.

**How honest the forecasts are.** Three strategies (trend pullback, breakout, reversal at a crowded extreme)
are replayed on ≈3.4 years of 1h candles with fees, slippage and funding. Numbers are tuned only on the first
70 %; what Orion reports comes from the last 30 %. A strategy is used for a coin only with ≥30 trades, a
positive result after costs and a profit factor ≥1.1. If none passes, Orion says it has no edge.

**Safety.** Hard limits in `trading_settings.json` (default: 2 % of the account at risk per trade, ≤10x,
≤6 % loss per day, ≤3 positions); isolated margin; the stop and target sit on the exchange; a position
without a stop is closed at once. The API key can trade but **cannot withdraw**; it is stored encrypted
(Windows DPAPI) and typed only in its own dialog. Orion never asks for the recovery phrase.

**Connecting (once).** Say „Свържи Hyperliquid“ → open app.hyperliquid-testnet.xyz, connect Trust Wallet, page
API → Generate → approve in Trust Wallet → paste the wallet address and the API key into Orion's dialog.
Start on the testnet; switch to real money only with „Мини на истински пари“ and its warning dialog.

**Test mode** practises trading every round: a $10 000 virtual account takes every signal on live prices, the
strategy lab tries other numbers (promoted only after beating the current ones on unseen history AND in 20
practice trades), and once a day a minimum-size testnet order checks that stops and targets are placed.
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "README: crypto forecasts and Hyperliquid trading"
```

- [ ] **Step 7: The testnet run with sir (manual — sir does the wallet steps)**

Walk sir through, one step at a time, in Bulgarian:
1. On app.hyperliquid-testnet.xyz connect Trust Wallet; get test USDC (the faucet on the testnet site; if it asks for a mainnet deposit first, say so and stop — that is sir's call).
2. Page API → Generate → approve in Trust Wallet → in Orion say „Свържи Hyperliquid“ → paste the address and the key → Orion says the balance.
3. „Отвори лонг на биткойн“ → read the dialog together → „Одобри сделката“ → on the testnet site the position shows with a TP and an SL order.
4. „Какви позиции имам?“ → matches the site; the top-bar chip shows `trading · TESTNET · BTC LONG …`.
5. „Затвори биткойна“ → „Затвори“ → the position and both trigger orders are gone on the site.
Report to sir what worked and anything that did not, with the exact messages. Mainnet stays off until sir decides.
