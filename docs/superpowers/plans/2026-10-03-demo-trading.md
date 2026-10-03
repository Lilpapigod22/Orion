# Demo Accounts, History Simulation and Mode Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Orion trades named demo accounts by itself (virtual money, live prices), simulates the strategies on history with compounding, stops saying "I can't manage an account", and shows three mode buttons — TEST MODE, DEMO TEST, REAL TRADE.

**Architecture:** A virtual exchange `orion/trading/demo.py` (one engine for demo accounts and the lab's practice account), `simulate.py` (portfolio replay of the backtest trades), `modes.py` (the two trading buttons: settings + window switch + sentence). The watch fetches each coin once per scan and feeds the journal, real alerts (REAL TRADE), and the demo/practice step (DEMO TEST); the lab's CPU-heavy search leaves the sandbox lock. Test mode returns to skills + understanding only. Skills route open/close to the demo or the real account.

**Tech Stack:** Python 3.12, pytest; React 19 + Vite 8 + Vitest.

**Spec:** `docs/superpowers/specs/2026-10-03-demo-trading-design.md` (builds on `docs/superpowers/specs/2026-10-03-crypto-trading-design.md`)

## Global Constraints

- Branch `crypto-trading` (in place). Never push or merge without sir asking.
- Real orders: only through `exchange.place/close` with approval, only while REAL TRADE (`settings.enabled()`) is on; REAL TRADE default **off**; DEMO TEST (`settings.demo_on()`) default **off**.
- Demo trades never touch the exchange; demo accounts are in US dollars; лева/евро converted at today's rate (BGN = EUR × 1.95583).
- Demo and practice trades are settled with the backtest's `exit_walk`, `result_r`, `funding_cost`; demo accounts hold one position per coin; the practice account one per coin + strategy + variant.
- Demo accounts trade only strategies that pass `backtest.is_enabled` unless the account has `all_signals`.
- Default new account: name „демо N“, 2 % risk, checked strategies; balance ≥ 10 $; risk 0 < r ≤ 10 %.
- Journal lines for demo trades, no voice. Real alerts only with REAL TRADE on.
- The lab's `search` (minutes of CPU) and `exchange.testnet_check()` never run while holding test mode's sandbox lock.
- Spoken texts in Bulgarian; window labels in English; numbers with a space as the thousands separator in new texts (`1 234.56 $`).
- No automated test touches the network or sends an order.

## Review Focus

1. Sir's own words „искам да тренираш сметка която е с 1000 долара и да направиш 10 000 лв чисто симулационно“ → a demo account with 1000 $, never „не мога“. (Test in Task 6.)
2. Both buttons off and sir says „отвори лонг на биткойн“ → Orion names the two buttons; no order anywhere. (Test in Task 4.)
3. REAL TRADE on but sir says „…в демото“ → the demo account, never a real order. (Test in Task 4.)
4. The lab search runs for minutes → reminders and price alerts are not blocked (the sandbox lock is free during the search). (Test in Task 5.)
5. DEMO TEST switched on with no account yet → „демо 1“ with 1000 $ is created and announced instead of silently doing nothing. (Test in Task 2.)

## File Structure

| File | Change |
|---|---|
| `orion/trading/__init__.py` | `on_switch` hook |
| `orion/trading/settings.py` | `demo` switch; REAL TRADE (`enabled`) default off |
| `orion/trading/demo.py` | NEW — virtual accounts, engine, step |
| `orion/trading/practice.py` | on the demo engine; `step()` replaces `run()`; testnet scheduling |
| `orion/trading/lab.py` | `judge` / `due` / `search` / `start` (step kept) |
| `orion/trading/modes.py` | NEW — `set_demo`, `set_real` |
| `orion/trading/simulate.py` | NEW — history simulation |
| `orion/trading/texts.py` | demo and simulation sentences |
| `orion/trading/exchange.py` | the "not connected" sentence points to the demo |
| `orion/trading/watcher.py` | one fetch per scan; real alerts gated; demo + practice step; lab outside the lock; chip with demo |
| `skills/crypto_trading_skills.py` | routing + 8 new skills |
| `orion/self_test.py` | back to skills + understanding every round (no trading stage) |
| `app.py` | start-up switch states, `on_switch` hook, `set_demo_mode` / `set_real_trading` |
| `orion/reflexes.py`, `orion/router.py`, `orion/brain.py`, `config.py`, `orion/self_test_cases.py` | phrases, words, nudge, persona, asks |
| `web/src/…` | two switches, their API calls, demo chip |
| `README.md` | the three buttons, demo, simulation |

---
### Task 1: The DEMO TEST switch in the settings, REAL TRADE off by default

**Files:**
- Modify: `orion/trading/settings.py`, `orion/trading/__init__.py`
- Test: `tests/test_trading_settings.py`, `tests/test_trading_skills.py` (fixture only)

**Interfaces:**
- Produces: `settings.demo_on() -> bool`, `settings.set_demo(on: bool) -> None`; `settings.enabled()` default False; `trading.on_switch: Callable[[str, bool], None]` (app.py replaces it; names `"demo"`, `"real"`)

- [ ] **Step 1: Write the failing test**

In `tests/test_trading_settings.py`, find:

```python
    assert settings.network() == "testnet" and settings.enabled()
```

and replace with:

```python
    assert settings.network() == "testnet" and not settings.enabled() and not settings.demo_on()
```

Find:

```python
def test_network_and_switch_are_saved():
```

and add directly ABOVE it:

```python
def test_the_demo_test_switch_is_saved():
    settings.set_demo(True)
    assert settings.demo_on()
    settings.set_demo(False)
    assert not settings.demo_on()


```

In `tests/test_trading_skills.py`, find:

```python
    monkeypatch.setattr(module.settings, "SETTINGS_FILE", tmp_path / "settings.json")
```

and add right after it:

```python
    module.settings.set_enabled(True)  # REAL TRADE on — these tests are about the real path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_settings.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'orion.trading.settings' has no attribute 'demo_on'` and the default test fails on `enabled()`

- [ ] **Step 3: Implement**

In `orion/trading/settings.py`, find:

```python
    "enabled": True,
```

and replace with:

```python
    "enabled": False,      # REAL TRADE button — real orders only while it is on
    "demo": False,         # DEMO TEST button — Orion trades the demo accounts by itself
```

Find:

```python
def account(net: str) -> tuple[str, str] | None:
```

and add directly ABOVE it:

```python
def demo_on() -> bool:
    return bool(load()["demo"])


def set_demo(on: bool) -> None:
    settings = load()
    settings["demo"] = bool(on)
    save(settings)


```

In `orion/trading/__init__.py`, find:

```python
show_key_dialog: Callable[[str], None] = lambda network: None
```

and add right after it:

```python
# app.py replaces it: moves a button in the window ("demo" = DEMO TEST, "real" = REAL TRADE).
on_switch: Callable[[str, bool], None] = lambda name, on: None
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_trading_settings.py tests/test_trading_skills.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orion/trading/settings.py orion/trading/__init__.py tests/test_trading_settings.py tests/test_trading_skills.py
git commit -m "Trading settings: DEMO TEST switch; REAL TRADE off by default"
```

---

### Task 2: The demo engine, practice on it, the lab split, the two buttons' logic

**Files:**
- Create: `orion/trading/demo.py`, `orion/trading/modes.py`
- Replace: `orion/trading/practice.py`, `orion/trading/lab.py` (whole files)
- Test: `tests/test_trading_demo.py` (new), `tests/test_trading_modes.py` (new), `tests/test_trading_practice.py` (one test replaced)

**Interfaces:**
- Consumes: `backtest.exit_walk/result_r/funding_cost/is_enabled`, `signals.Signal/latest/LABELS`, `risk.Limits`, `settings`, `trading.on_switch`
- Produces:
  - `demo.DEMO_FILE`, `load() -> {"accounts": {name: account}, "active": name|None}`, `save(book)`, `new_account(balance, risk_pct=2.0, all_signals=False) -> dict`, `to_usd(amount, currency) -> float`, `create(name, balance, risk_pct=2.0, all_signals=False) -> str` (the name), `delete(text) -> str`, `reset(text="") -> list[str]`, `choose(text) -> str`, `active(book) -> str|None`, `find(book, text) -> str|None`, `open_signals(account, found, variant="current", limits=None, per_coin=True) -> list[dict]`, `open_manual(account, coin, side, entry, stop, target, strategy, limits=None) -> dict`, `close_manual(account, coin, price) -> list[dict]`, `settle(account, bars_by_coin, funding_by_coin) -> list[dict]`, `by_strategy(account, variant="current") -> dict`, `equity(account, mids) -> float`, `step(book, prepared_by_coin, report) -> list[str]`, `_lock` (RLock), `_eur_per_usd()` (test seam)
  - `practice.step(prepared_by_coin) -> Round`, `practice.testnet_due() -> bool`, `practice.mark_testnet()`; `open_signals/settle/by_strategy/load/save/Round` keep their signatures
  - `lab.judge(practice_state) -> str`, `lab.due() -> str|None`, `lab.start(strategy, found, log=print) -> str`, `lab.search` and `lab.step` unchanged
  - `modes.set_demo(on) -> str`, `modes.set_real(on) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trading_demo.py`:

```python
from types import SimpleNamespace

import pytest

from orion.trading import demo, signals
from orion.trading.data import HOUR, Bars
from orion.trading.signals import Signal

GOOD = {"trades": 40, "win_rate": 0.5, "win_low": 0.35, "win_high": 0.65, "avg_r": 0.3, "profit_factor": 1.6,
        "max_drawdown_r": 5.0}


@pytest.fixture(autouse=True)
def temp_book(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "demo.json")


def sig(coin="BTC", time=10 * HOUR, strategy="breakout", side="long"):
    return Signal(coin, strategy, side, time, 100.0, 99.0, 102.0, 4, ["пробив"])


def candles(rows, start=10 * HOUR):
    bars = Bars(HOUR)
    for k, (o, h, l, c) in enumerate(rows):
        bars.add(start + k * HOUR, o, h, l, c, 1.0)
    return bars


def test_accounts_get_names_and_checked_settings():
    assert demo.create("", 1000) == "демо 1"
    assert demo.create("", 500) == "демо 2"
    assert demo.create("предпазлива", 500, risk_pct=1) == "предпазлива"
    book = demo.load()
    assert book["active"] == "предпазлива" and book["accounts"]["демо 1"]["balance"] == 1000
    with pytest.raises(ValueError, match="Вече има"):
        demo.create("демо 1", 100)
    with pytest.raises(ValueError, match="поне 10"):
        demo.create("x", 5)
    with pytest.raises(ValueError, match="между"):
        demo.create("x", 100, risk_pct=20)


def test_delete_reset_and_choose_by_the_spoken_name():
    demo.create("", 1000)
    demo.create("Предпазлива", 500, risk_pct=1)
    assert demo.choose("демо 1") == "демо 1" and demo.load()["active"] == "демо 1"
    book = demo.load()
    book["accounts"]["демо 1"]["balance"] = 1234.0
    demo.save(book)
    assert demo.reset("демо 1") == ["демо 1"] and demo.load()["accounts"]["демо 1"]["balance"] == 1000
    assert demo.delete("предпазливата") == "Предпазлива"
    assert list(demo.load()["accounts"]) == ["демо 1"]
    with pytest.raises(ValueError, match="Няма демо сметка"):
        demo.delete("никаква")
    assert demo.reset("") == ["демо 1"]


def test_leva_and_euro_are_converted_to_dollars(monkeypatch):
    monkeypatch.setattr(demo, "_eur_per_usd", lambda: 0.9)
    assert demo.to_usd(1000, "долара") == 1000
    assert demo.to_usd(1955.83, "лева") == pytest.approx(1000 / 0.9)
    assert demo.to_usd(900, "евро") == pytest.approx(1000)
    with pytest.raises(ValueError):
        demo.to_usd(1, "йени")


def test_demo_accounts_hold_one_position_per_coin():
    account = demo.new_account(1000)
    opened = demo.open_signals(account, [sig(), sig(strategy="pullback")])
    assert len(opened) == 1 and opened[0]["size"] == pytest.approx(20.0)   # 2 % of 1000 $ over a 1 $ stop
    assert demo.open_signals(account, [sig(coin="ETH")])[0]["coin"] == "ETH"


def test_manual_trades_and_closing_at_market():
    account = demo.new_account(1000, risk_pct=1)
    trade = demo.open_manual(account, "SOL", "short", 100.0, 101.0, 98.0, "без сигнал")
    assert trade["size"] == pytest.approx(10.0)
    with pytest.raises(ValueError, match="вече има позиция"):
        demo.open_manual(account, "SOL", "long", 100.0, 99.0, 102.0, "без сигнал")
    closed = demo.close_manual(account, "SOL", 99.0)
    assert len(closed) == 1 and closed[0]["why"] == "ръчно" and account["open"] == []
    assert account["balance"] > 1000                        # a short from 100 to 99, after the costs
    assert demo.close_manual(account, "BTC", 1.0) == []


def test_step_trades_only_checked_strategies_unless_all_signals(monkeypatch):
    report = {"time": 0, "coins": {"BTC": {"breakout": GOOD}}}
    book = {"accounts": {"демо 1": demo.new_account(1000), "смел": demo.new_account(1000, all_signals=True)},
            "active": "демо 1"}
    p = SimpleNamespace(h1=candles([(100.0, 100.5, 99.5, 100.0)]), funding_t=[], funding_v=[])
    monkeypatch.setattr(signals, "latest", lambda p_: [sig(strategy="pullback"), sig()])
    lines = demo.step(book, {"BTC": p}, report)
    assert [t["strategy"] for t in book["accounts"]["демо 1"]["open"]] == ["breakout"]
    assert [t["strategy"] for t in book["accounts"]["смел"]["open"]] == ["pullback"]
    assert any(line.startswith("DEMO демо 1: отворих лонг на биткойн") for line in lines)


def test_step_settles_and_reports_the_result(monkeypatch):
    account = demo.new_account(1000)
    demo.open_signals(account, [sig()])
    book = {"accounts": {"демо 1": account}, "active": "демо 1"}
    p = SimpleNamespace(h1=candles([(100.0, 100.5, 99.5, 100.2), (100.2, 102.3, 100.0, 102.0)]), funding_t=[],
                        funding_v=[])
    monkeypatch.setattr(signals, "latest", lambda p_: [])
    lines = demo.step(book, {"BTC": p}, None)
    assert account["open"] == [] and account["balance"] > 1000
    assert lines[0].startswith("DEMO демо 1: затворих лонг на биткойн (цел): +")
    assert demo.by_strategy(account) == {"breakout": {"n": 1, "wins": 1, "r": pytest.approx(1.87, abs=0.01)}}


def test_equity_counts_open_positions():
    account = demo.new_account(1000)
    demo.open_signals(account, [sig()])                    # long 20 BTC from 100
    assert demo.equity(account, {"BTC": 101.0}) == pytest.approx(1020.0)
    assert demo.equity(account, {}) == 1000.0
```

Create `tests/test_trading_modes.py`:

```python
import pytest

from orion import trading
from orion.trading import demo, modes, settings


@pytest.fixture(autouse=True)
def switched(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "s.json")
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "demo.json")
    calls = []
    monkeypatch.setattr(trading, "on_switch", lambda name, on: calls.append((name, on)))
    return calls


def test_demo_test_on_creates_the_first_account(switched):
    text = modes.set_demo(True)
    assert "„демо 1“ с 1000 долара" in text and settings.demo_on()
    assert list(demo.load()["accounts"]) == ["демо 1"] and switched == [("demo", True)]
    assert "„демо 1“" in modes.set_demo(True)
    assert len(demo.load()["accounts"]) == 1
    assert "Спрях демо теста" in modes.set_demo(False) and not settings.demo_on()


def test_real_trade_says_what_is_missing(switched, monkeypatch):
    assert "не е свързан" in modes.set_real(True) and settings.enabled()
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    assert "„Одобри“" in modes.set_real(True)
    assert "Спрях истинската търговия" in modes.set_real(False) and not settings.enabled()
    assert ("real", False) in switched
```

In `tests/test_trading_practice.py`, find the whole test that starts with:

```python
def test_a_round_opens_settles_and_checks_the_testnet_once_a_day(monkeypatch):
```

and ends with:

```python
    assert "тренировъчната сметка е 10 000 $ (+0.0 %)" in first.summary()
```

and replace it with:

```python
def test_a_step_opens_and_settles_and_the_testnet_check_is_due_once_a_day(monkeypatch):
    p = fake_prepared()
    monkeypatch.setattr(signals, "latest", lambda p_: [Signal("BTC", "pullback", "long", p.h1.end(len(p.h1) - 1),
                                                              p.h1.c[-1], p.h1.c[-1] * 0.99, p.h1.c[-1] * 1.02, 4, [])])
    prepared = {"BTC": p, "ETH": p, "SOL": p}
    first = practice.step(prepared)
    assert first.opened == 1 and first.balance == 10_000.0
    assert practice.step(prepared).opened == 0
    assert practice.load()["open"][0]["variant"] == "current"
    assert "тренировъчната сметка е 10 000 $ (+0.0 %)" in first.summary()
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    assert practice.testnet_due()
    practice.mark_testnet()
    assert not practice.testnet_due()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trading_demo.py tests/test_trading_modes.py tests/test_trading_practice.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'demo'`, `cannot import name 'modes'`, `practice` has no `step`

- [ ] **Step 3: Write `orion/trading/demo.py`**

```python
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
```

- [ ] **Step 4: Replace `orion/trading/lab.py` with:**

```python
"""
The strategy lab (DEMO TEST): tries other numbers for one strategy at a time. A variant replaces the current
numbers only through two gates — (a) on the history it beats them on the 30 % no tuning saw and passes the
enable rule, then (b) it also beats them over its first 20 practice trades, run side by side. Only numbers
change; code changes still need „Одобри и включи“.

The watch runs the steps separately: judge / due / start touch files (under test mode's sandbox lock);
search is minutes of CPU on the candle cache and runs without the lock.
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


def _now() -> int:
    return int(time.time() * 1000)


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


def judge(practice_state: dict) -> str:
    """Gate (b): every trial with 20 practice trades is promoted or dropped. Returns what changed."""
    state = load()
    notes = []
    now = _now()
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
    save(state)
    return "; ".join(notes)


def due() -> str | None:
    """The strategy to search next: not on trial and not searched for a week — the oldest first."""
    state = load()
    week = SEARCH_EVERY_DAYS * 24 * 3_600_000
    now = _now()
    free = [s for s in STRATEGIES if s not in state["candidates"] and now - state["searched"].get(s, 0) >= week]
    return min(free, key=lambda s: state["searched"].get(s, 0)) if free else None


def start(strategy: str, found, log=print) -> str:
    """Gate (a)'s verdict: records the search and starts a trial if the variant passed. Returns what changed."""
    state = load()
    now = _now()
    state["searched"][strategy] = now
    note = ""
    if found:
        numbers, new, old = found
        if new.enabled and better(new.avg_r, old.avg_r):
            state["candidates"][strategy] = {"params": numbers, "since": now, "oos": asdict(new)}
            note = f"пробвам нови числа за „{LABELS[strategy]}“ в тренировката"
            log(f"Лаборатория: {LABELS[strategy]} {numbers} — {new.avg_r:+.2f}R срещу {old.avg_r:+.2f}R")
    save(state)
    return note


def step(practice_state: dict, log=print, markets_by_coin: dict | None = None) -> str:
    """judge + one search, all at once (the watch runs the search outside the lock instead)."""
    notes = [judge(practice_state)]
    strategy = due()
    if strategy:
        if markets_by_coin is None:
            markets_by_coin = {coin: market.history(coin) for coin in COINS}
        notes.append(start(strategy, search(strategy, markets_by_coin), log))
    return "; ".join(note for note in notes if note)
```

- [ ] **Step 5: Replace `orion/trading/practice.py` with:**

```python
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
```

- [ ] **Step 6: Write `orion/trading/modes.py`**

```python
"""
The two trading buttons — DEMO TEST and REAL TRADE: the setting, the button in the window (trading.on_switch)
and what Orion says. The skills, the reflexes and the window all go through here.
"""
from .. import trading
from . import demo, settings


def set_demo(on: bool) -> str:
    settings.set_demo(on)
    trading.on_switch("demo", bool(on))
    if not on:
        return ("Спрях демо теста. Демо сметките чакат — отворените им сделки ще се приключат по свещите, когато "
                "го включите пак.")
    book = demo.load()
    if not book["accounts"]:
        demo.create("демо 1", 1000.0)
        return ("Включих демо теста и направих демо сметка „демо 1“ с 1000 долара и 2 % риск. Търгувам сам по "
                "проверените стратегии, на истински цени, без истински пари.")
    names = ", ".join(f"„{name}“" for name in book["accounts"])
    return f"Включих демо теста — търгувам сам на демо сметките {names}, без истински пари."


def set_real(on: bool) -> str:
    settings.set_enabled(on)
    trading.on_switch("real", bool(on))
    if not on:
        return ("Спрях истинската търговия — няма да отварям истински сделки. Отворените позиции остават със "
                "стоповете си.")
    network = settings.network()
    where = "тестовата мрежа" if network == "testnet" else "ИСТИНСКИ пари"
    if not settings.account(network):
        return f"Включих REAL TRADE ({where}), но Hyperliquid не е свързан — кажете „свържи Hyperliquid“."
    return f"Включих REAL TRADE ({where}). Давам прогнози, когато питате, и всяка сделка чака Вашето „Одобри“."
```

- [ ] **Step 7: Run the tests**

Run: `python -m pytest tests/test_trading_demo.py tests/test_trading_modes.py tests/test_trading_practice.py -q -p no:cacheprovider`
Expected: PASS

Run: `python -m pytest -q -p no:cacheprovider`
Expected: PASS (all). Test mode's `_practice` still calls `practice.run`, which no longer exists — no test runs it
(its test replaces `_practice`), and Task 5 removes the trading stage from test mode altogether.

- [ ] **Step 8: Commit**

```bash
git add orion/trading/demo.py orion/trading/modes.py orion/trading/practice.py orion/trading/lab.py tests/test_trading_demo.py tests/test_trading_modes.py tests/test_trading_practice.py
git commit -m "Demo engine: named virtual accounts; practice on it; lab split; DEMO TEST / REAL TRADE logic"
```

---
### Task 3: The history simulation and the new sentences

**Files:**
- Create: `orion/trading/simulate.py`
- Modify: `orion/trading/texts.py` (new functions at the end, one import)
- Test: `tests/test_trading_simulate.py`

**Interfaces:**
- Consumes: `backtest.simulate/is_enabled/Trade`, `market.history`, `signals.STRATEGIES`, `demo.equity/active`
- Produces: `simulate.Result(start, final, trades, wins, max_drawdown_pct, months={}, days=365, strategies={})` with `.return_pct`; `simulate.run(balance, days=365, risk_pct=2.0, all_signals=False, report=None, markets=None) -> Result`; `texts.simulation(result, risk_pct, all_signals)`, `texts.demo_created(name, usd, risk_pct, all_signals, amount, currency)`, `texts.demo_status(book, mids, on)`, `texts.demo_opened(name, trade)`, `texts.demo_closed(name, trades, account)`, `texts._usd(value)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_simulate.py`:

```python
from types import SimpleNamespace

import pytest

from orion.trading import backtest, demo, simulate, texts
from orion.trading.backtest import Trade
from orion.trading.data import HOUR, Bars

DAY = 24 * HOUR
GOOD = {"trades": 40, "win_rate": 0.5, "win_low": 0.35, "win_high": 0.65, "avg_r": 0.3, "profit_factor": 1.6,
        "max_drawdown_r": 5.0}


def markets():
    clock = Bars(HOUR, t=list(range(0, 400 * DAY, HOUR)))     # 400 days — only the clock matters here
    return {coin: SimpleNamespace(h1=clock, coin=coin) for coin in ("BTC", "ETH", "SOL")}


def trade(coin, strategy, entry_day, exit_day, r):
    return Trade(coin, strategy, "long", entry_day * DAY, exit_day * DAY, 100.0, 100.0, 99.0, 102.0, r, "цел")


def replay(monkeypatch, trades, enabled, **kwargs):
    calls = []

    def fake(p, strategy, start, end):
        calls.append((p.coin, strategy, start, end))
        return [t for t in trades if t.coin == p.coin and t.strategy == strategy]

    monkeypatch.setattr(backtest, "simulate", fake)
    report = {"time": 0, "coins": {coin: {s: GOOD for s in names} for coin, names in enabled.items()}}
    return simulate.run(1000.0, report=report, markets=markets(), **kwargs), calls


def test_compounding_and_the_drawdown(monkeypatch):
    result, _ = replay(monkeypatch, [trade("BTC", "breakout", 100, 101, 2), trade("BTC", "breakout", 102, 103, -1)],
                       {"BTC": ["breakout"]})
    assert result.final == pytest.approx(1019.2)               # +40 on 1000, then −20.8 on 1040
    assert (result.trades, result.wins) == (2, 1)
    assert result.max_drawdown_pct == pytest.approx(2.0)
    assert list(result.months.values()) == [pytest.approx(1.92)]
    assert result.return_pct == pytest.approx(1.92)


def test_one_position_per_coin_but_coins_trade_together(monkeypatch):
    trades = [trade("BTC", "breakout", 100, 110, 1), trade("BTC", "pullback", 101, 102, 1),
              trade("ETH", "breakout", 101, 102, -1)]
    result, _ = replay(monkeypatch, trades, {"BTC": ["breakout", "pullback"], "ETH": ["breakout"]})
    assert (result.trades, result.wins, result.final) == (2, 1, pytest.approx(1000.0))
    assert result.max_drawdown_pct == pytest.approx(2.0)


def test_only_checked_strategies_unless_all_signals(monkeypatch):
    result, calls = replay(monkeypatch, [], {"BTC": ["breakout"]})
    assert [(c, s) for c, s, _, _ in calls] == [("BTC", "breakout")]
    assert result.strategies == {"BTC": ["breakout"], "ETH": [], "SOL": []}
    _, calls = replay(monkeypatch, [], {}, all_signals=True)
    assert len(calls) == 9


def test_the_window_starts_days_before_the_last_candle(monkeypatch):
    _, calls = replay(monkeypatch, [], {"BTC": ["breakout"]}, days=30)
    assert calls[0][2:] == ((400 - 30) * 24, 400 * 24)


def test_what_orion_says():
    result = simulate.Result(1000.0, 1019.2, 2, 1, 2.0, {"04.2026": 1.92, "05.2026": -0.5}, 365,
                             {"BTC": ["breakout"], "ETH": [], "SOL": []})
    text = texts.simulation(result, 2.0, False)
    assert "проверените стратегии (пробив на биткойн)" in text
    assert "накрая 1 019.20 $ (+1.9 %)" in text and "Най-голямо падане 2.0 %" in text
    assert "Най-добър месец 04.2026 (+1.9 %), най-лош 05.2026 (-0.5 %)" in text
    assert text.endswith("Миналото не гарантира бъдещето.")
    empty = simulate.Result(1000.0, 1000.0, 0, 0, 0.0, {}, 365, {"BTC": [], "ETH": [], "SOL": []})
    assert "Нито една стратегия не мина проверката" in texts.simulation(empty, 2.0, False)


def test_demo_sentences(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "demo.json")
    assert texts.demo_created("демо 1", 1111.111, 1.0, False, 1955.83, "лева") == (
        "Направих демо сметка „демо 1“ с 1 111.11 $ (1 956 лева) и 1 % риск — само проверените стратегии. "
        "Парите са измислени, цените — истински.")
    account = demo.new_account(1000)
    account["open"].append({"coin": "BTC", "side": "long", "entry": 100.0, "size": 2.0})
    book = {"accounts": {"демо 1": account}, "active": "демо 1"}
    status = texts.demo_status(book, {"BTC": 110.0}, True)
    assert status.splitlines()[1] == ("„демо 1“: 1 020.00 $ (+2.0 % от 1 000.00 $), 0 приключени сделки, 0 на "
                                      "печалба, отворени: биткойн лонг (избрана).")
    assert "DEMO TEST е изключен" in texts.demo_status(book, {}, False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_simulate.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'simulate'`

- [ ] **Step 3: Write `orion/trading/simulate.py`**

```python
"""
„Симулирай 1000 долара за последната година“: the strategies replayed on history across the three coins with
compounding — one position per coin, the risk sized on the realised balance at each entry, fees, slippage and
funding as in the backtest. Only the strategies that passed the honest check, unless all_signals. Results are
in R, so a live trade's leverage cap is not applied here.
"""
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime

from . import COINS, backtest, data, market, signals


@dataclass
class Result:
    start: float
    final: float
    trades: int
    wins: int
    max_drawdown_pct: float
    months: dict = field(default_factory=dict)      # "MM.YYYY" -> % change in that month
    days: int = 365
    strategies: dict = field(default_factory=dict)  # coin -> the strategies used

    @property
    def return_pct(self) -> float:
        return (self.final / self.start - 1) * 100


def run(balance: float, days: int = 365, risk_pct: float = 2.0, all_signals: bool = False,
        report: dict | None = None, markets: dict | None = None) -> Result:
    markets = markets if markets is not None else {coin: market.history(coin) for coin in COINS}
    trades, used = [], {}
    for coin, p in markets.items():
        end = p.h1.end(len(p.h1) - 1)
        start = bisect_left(p.h1.t, end - days * 24 * data.HOUR)
        used[coin] = [s for s in signals.STRATEGIES if all_signals or backtest.is_enabled(report, coin, s)]
        for strategy in used[coin]:
            trades += backtest.simulate(p, strategy, start, len(p.h1))
    trades.sort(key=lambda t: (t.entry_time, t.coin))

    cash = peak = float(balance)
    drawdown = 0.0
    busy: dict[str, int] = {}
    pending: list[tuple[int, object, float]] = []   # (exit time, trade, risk in $)
    months: dict[str, list[float]] = {}             # month -> [balance at its first exit, P/L]
    taken = wins = 0

    def realise(until: float) -> None:
        nonlocal cash, peak, drawdown, wins
        for item in sorted((x for x in pending if x[0] <= until), key=lambda x: x[0]):
            pending.remove(item)
            exit_time, trade, risk_usd = item
            month = months.setdefault(datetime.fromtimestamp(exit_time / 1000).strftime("%m.%Y"), [cash, 0.0])
            pnl = trade.r * risk_usd
            month[1] += pnl
            cash += pnl
            wins += pnl > 0
            peak = max(peak, cash)
            drawdown = max(drawdown, (peak - cash) / peak * 100 if peak > 0 else 0.0)

    for trade in trades:
        if busy.get(trade.coin, -1) > trade.entry_time:
            continue  # one position per coin
        realise(trade.entry_time)
        if cash <= 0:
            break
        busy[trade.coin] = trade.exit_time
        pending.append((trade.exit_time, trade, cash * risk_pct / 100))
        taken += 1
    realise(float("inf"))
    return Result(float(balance), cash, taken, wins, drawdown,
                  {m: pnl / first * 100 for m, (first, pnl) in months.items()}, days, used)
```

- [ ] **Step 4: Add the sentences to `orion/trading/texts.py`**

Find:

```python
from . import NAMES, backtest
```

and replace with:

```python
from . import NAMES, backtest, demo
```

Append to `orion/trading/texts.py`:

```python


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
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_trading_simulate.py -q -p no:cacheprovider`
Expected: PASS

Run: `python -m pytest -q -p no:cacheprovider`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add orion/trading/simulate.py orion/trading/texts.py tests/test_trading_simulate.py
git commit -m "History simulation with compounding; demo and simulation sentences"
```

---

### Task 4: The skills — demo accounts, simulation, buttons, routing

**Files:**
- Replace: `skills/crypto_trading_skills.py` (whole file)
- Modify: `orion/trading/exchange.py` (the "not connected" sentence)
- Test: `tests/test_trading_demo_skills.py` (new), `tests/test_trading_skills.py` (one assertion)

**Interfaces:**
- Consumes: `demo.*`, `modes.set_demo/set_real`, `simulate.run/Result`, `texts.*`, `data.assets`
- Produces (skill names used by Task 6's reflexes): `create_demo_account(balance, name="", currency="USD", risk_pct=2.0, all_signals=False)`, `demo_status()`, `delete_demo_account(name)`, `reset_demo_account(name="")`, `choose_demo_account(name)`, `simulate_history(balance, days=365, currency="USD", risk_pct=2.0, all_signals=False)`, `set_demo_test(on)`, `set_real_trading(on)`, `open_trade(coin, side, account="")`, `close_trade(coin, account="")`; `pause_trading`/`resume_trading` move REAL TRADE

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trading_demo_skills.py`:

```python
import copy
import sys

import pytest

import config
from orion import trading
from orion.tools import registry
from orion.trading import data, signals, simulate
from test_trading_signals import random_walk


@pytest.fixture
def cts(monkeypatch, tmp_path):
    if not registry.names():
        registry.load_skills(config.SKILLS_DIR)
    module = sys.modules["skills.crypto_trading_skills"]
    monkeypatch.setattr(module.journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(module.settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(module.demo, "DEMO_FILE", tmp_path / "demo.json")
    monkeypatch.setattr(module.demo, "_eur_per_usd", lambda: 0.9)
    monkeypatch.setattr(module.backtest, "load", lambda: None)
    monkeypatch.setattr(module.backtest, "refresh_async", lambda lock=None: True)
    h1 = random_walk(1200)
    prepared = signals.prepare("BTC", h1, data.resample(h1, 4 * data.HOUR), data.resample(h1, 24 * data.HOUR), [],
                               copy.deepcopy(signals.DEFAULTS))
    monkeypatch.setattr(module.market, "live", lambda coin, params=None: prepared)
    monkeypatch.setattr(module.data, "assets",
                        lambda: {c: data.Asset(c, 100.0, 100.0, 0.0, 0.0, 0.0, 2, 20) for c in ("BTC", "ETH", "SOL")})
    monkeypatch.setattr(module.signals, "latest", lambda p: [])
    return module


def test_creating_demo_accounts(cts):
    text = cts.create_demo_account(1000)
    assert text.startswith("Направих демо сметка „демо 1“ с 1 000.00 $") and "DEMO TEST" in text
    text = cts.create_demo_account(1955.83, name="предпазлива", currency="лева", risk_pct=1)
    assert "„предпазлива“ с 1 111.11 $ (1 956 лева) и 1 % риск" in text
    assert "Вече има" in cts.create_demo_account(10, name="предпазлива")


def test_trades_go_to_the_demo_when_only_demo_test_is_on(cts):
    cts.settings.set_demo(True)
    cts.create_demo_account(1000)
    assert cts.open_trade("биткойн", "лонг").startswith("DEMO „демо 1“: отворих лонг на биткойн на 100.00")
    status = cts.demo_status()
    assert "„демо 1“" in status and "отворени: биткойн лонг" in status
    assert cts.close_trade("биткойна").startswith("DEMO „демо 1“: затворих биткойн (")
    assert cts.demo.load()["accounts"]["демо 1"]["open"] == []


def test_both_buttons_off_says_which_to_switch_on(cts):
    answer = cts.open_trade("BTC", "long")
    assert "DEMO TEST" in answer and "REAL TRADE" in answer


def test_saying_in_the_demo_overrides_real_trade(cts, monkeypatch):
    cts.settings.set_enabled(True)
    cts.create_demo_account(1000)
    monkeypatch.setattr(cts.exchange, "place", lambda *args, **kwargs: pytest.fail("no real order"))
    assert cts.open_trade("BTC", "long", account="демо").startswith("DEMO „демо 1“")


def test_no_demo_account_yet(cts):
    cts.settings.set_demo(True)
    assert "направи демо сметка" in cts.open_trade("BTC", "long")


def test_delete_reset_choose(cts):
    cts.create_demo_account(1000)
    cts.create_demo_account(500, name="смел")
    assert cts.choose_demo_account("демо 1") == "Избрах демо сметката „демо 1“."
    assert cts.reset_demo_account("смел") == "Започнах отначало: „смел“."
    assert cts.delete_demo_account("смел") == "Изтрих демо сметката „смел“."
    assert "Няма демо сметка" in cts.delete_demo_account("смел")


def test_buttons_by_voice(cts, monkeypatch):
    switched = []
    monkeypatch.setattr(trading, "on_switch", lambda name, on: switched.append((name, on)))
    assert "Включих демо теста" in cts.set_demo_test(True)
    assert "Спрях истинската търговия" in cts.pause_trading()
    assert "Включих REAL TRADE" in cts.set_real_trading(True)
    assert switched == [("demo", True), ("real", False), ("real", True)]


def test_the_simulation(cts, monkeypatch):
    monkeypatch.setattr(cts.backtest, "load", lambda: {"time": 0, "coins": {}})
    monkeypatch.setattr(cts.simulate, "run", lambda *args, **kwargs: simulate.Result(
        1000.0, 1100.0, 10, 6, 5.0, {"03.2026": 4.0}, 365, {"BTC": ["breakout"]}))
    text = cts.simulate_history(1000)
    assert "накрая 1 100.00 $ (+10.0 %)" in text and text.endswith("Миналото не гарантира бъдещето.")
    monkeypatch.setattr(cts.backtest, "load", lambda: None)
    assert cts.simulate_history(1000) == cts.texts.NO_REPORT


def test_without_a_key_orion_points_to_the_demo(cts):
    cts.settings.set_enabled(True)
    answer = cts.trading_positions()
    assert "свържи Hyperliquid" in answer and "направи демо сметка" in answer


def test_positions_and_account_show_the_demo_without_real_trade(cts):
    assert cts.trading_positions() == cts.NEITHER
    cts.create_demo_account(1000)
    assert cts.trading_positions().startswith("Демо сметките")
    assert cts.trading_account().startswith("Демо сметките")
```

In `tests/test_trading_skills.py`, find:

```python
    assert "спряна" in cts.open_trade("BTC", "long")
```

and replace with:

```python
    assert "DEMO TEST" in cts.open_trade("BTC", "long")       # REAL TRADE off, DEMO TEST off
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trading_demo_skills.py tests/test_trading_skills.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'skills.crypto_trading_skills' has no attribute 'create_demo_account'` (and the others)

- [ ] **Step 3: The "not connected" sentence**

In `orion/trading/exchange.py`, find:

```python
        raise TradingError("Hyperliquid не е свързан. Кажете „свържи Hyperliquid“.")
```

and replace with:

```python
        raise TradingError("Hyperliquid не е свързан. За истински пари кажете „свържи Hyperliquid“ и включете REAL "
                           "TRADE. Мога да търгувам на демо сметка — кажете „направи демо сметка с 1000 долара“.")
```

- [ ] **Step 4: Replace `skills/crypto_trading_skills.py` with:**

```python
"""
Крипто прогнози и търговия: биткойн, етериум и солана на Hyperliquid — и демо сметки с измислени пари.
Числата идват от кода (три стратегии с честна проверка върху историята). На демо сметките Орион търгува сам
(DEMO TEST); всяка истинска сделка чака „Одобри“ от сър (REAL TRADE).
"""
from datetime import datetime

from orion import confirm, markets, orion_tool, trading
from orion.trading import (COINS, NAMES, backtest, coin_from_text, data, demo, exchange, journal, market, modes,
                           risk, settings, signals, simulate, texts)

# The forecast chart — app.py shows it in the journal after crypto_forecast.
last_chart: dict | None = None
REFUSALS = (risk.RiskError, exchange.TradingError, ValueError)
MAINNET_WORDS = ("mainnet", "истински", "истински пари", "реални", "реални пари", "истинска", "истинската мрежа",
                 "за истински пари")
NEITHER = ("Включете DEMO TEST за демо сделки (без истински пари) или REAL TRADE за истински — с Вашето „Одобри“ "
           "за всяка сделка.")
NO_DEMO = "Нямате демо сметка — кажете „направи демо сметка с 1000 долара“."
RATE_DOWN = "Не мога да взема курса в момента — кажете сумата в долари."
_DEMO_WORDS = ("демо", "демото", "demo", "в демото")


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


def _to_demo(account: str) -> bool | None:
    """True — the demo account, False — the real account, None — neither button is on."""
    if account.strip():
        return True
    if settings.enabled():
        return False
    if settings.demo_on():
        return True
    return None


def _demo_name(book: dict, account: str) -> str:
    words = account.strip().lower()
    name = demo.find(book, account) if words and words not in _DEMO_WORDS else None
    name = name or demo.active(book)
    if not name:
        raise ValueError(NO_DEMO)
    return name


def _mids() -> dict:
    return {coin: asset.mid for coin, asset in data.assets().items()}


def _real_view() -> bool:
    """Positions/account questions: the real account with REAL TRADE on, or when a key is connected and the
    demo is not in use."""
    to_demo = _to_demo("")
    if to_demo is False:
        return True
    return to_demo is None and bool(settings.account(settings.network())) and not demo.load()["accounts"]


# --- Forecasts ---------------------------------------------------------------------------------
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


# --- Accounts and trades -------------------------------------------------------------------------
@orion_tool
def trading_positions() -> str:
    """Отворените позиции сега: в истинската сметка (REAL TRADE) или в демо сметките (DEMO TEST)."""
    if not _real_view():
        return demo_status() if demo.load()["accounts"] else NEITHER
    network = settings.network()
    try:
        state, _ = exchange.account_state(network)
    except REFUSALS as e:
        return str(e)
    return texts.positions_text(state, network)


@orion_tool
def trading_account() -> str:
    """Сметката: истинската в Hyperliquid (пари, днешна загуба, риск) или демо сметките."""
    if not _real_view():
        return demo_status() if demo.load()["accounts"] else NEITHER
    network = settings.network()
    try:
        state, _ = exchange.account_state(network)
    except REFUSALS as e:
        return str(e)
    return texts.account_text(state, network, settings.limits())


def _open_demo(account: str, coin: str, side: str, p, stop_gap: float, target_gap: float, strategy: str) -> str:
    try:
        price = _mids().get(coin) or p.h1.c[-1]
    except OSError:
        price = p.h1.c[-1]
    with demo._lock:
        book = demo.load()
        try:
            name = _demo_name(book, account)
            trade = demo.open_manual(book["accounts"][name], coin, side, price, price - stop_gap, price + target_gap,
                                     strategy, settings.limits())
        except ValueError as e:
            return str(e)
        demo.save(book)
    return texts.demo_opened(name, trade)


@orion_tool
def open_trade(coin: str, side: str, account: str = "") -> str:
    """Отваря сделка — лонг или шорт — на биткойн, етериум или солана. С DEMO TEST (или „в демото“) — веднага в
    демо сметката, без истински пари; с REAL TRADE — в Hyperliquid, след прозорец „Одобри“.

    Args:
        coin: Монетата — "биткойн", "етериум" или "солана".
        side: "лонг" (за покачване) или "шорт" (за спадане).
        account: "демо" или името на демо сметката, ако сделката е в демото; празно — според бутоните.
    """
    try:
        c, direction = coin_from_text(coin), _side(side)
    except ValueError as e:
        return str(e)
    to_demo = _to_demo(account)
    if to_demo is None:
        return NEITHER
    try:
        p = market.live(c)
    except OSError:
        return texts.NO_DATA
    signal = next((s for s in signals.latest(p) if s.side == direction), None)
    if signal:  # the distances of the signal — re-anchored to the price of the account it goes to
        stop_gap, target_gap = signal.entry - signal.stop, signal.target - signal.entry
        note, strategy = f"Сигнал: {signals.LABELS[signal.strategy]}, сила {signal.strength} от 5.", signal.strategy
    else:
        atr = p.s["atr1"][-1] or p.h1.c[-1] * 0.01
        sign = 1 if direction == "long" else -1
        stop_gap, target_gap = sign * 1.5 * atr, sign * 3.0 * atr
        note, strategy = "ВНИМАНИЕ: в момента няма сигнал в тази посока — влизате без сигнал.", "без сигнал"
    if to_demo:
        return _open_demo(account, c, direction, p, stop_gap, target_gap, strategy)
    network = settings.network()
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
def close_trade(coin: str, account: str = "") -> str:
    """Затваря позиция (или всички): в демо сметката — веднага; в Hyperliquid — след „Одобри“ от сър.

    Args:
        coin: Монетата ("биткойн", "етериум", "солана") или "всички".
        account: "демо" или името на демо сметката, ако е в демото; празно — според бутоните.
    """
    to_demo = _to_demo(account)
    if to_demo is None:
        return NEITHER
    try:
        coins = list(COINS) if coin.strip().lower() in ("всички", "всичко", "all") else [coin_from_text(coin)]
    except ValueError as e:
        return str(e)
    if to_demo:
        try:
            mids = _mids()
        except OSError:
            return texts.NO_DATA
        with demo._lock:
            book = demo.load()
            try:
                name = _demo_name(book, account)
            except ValueError as e:
                return str(e)
            chosen = book["accounts"][name]
            closed = [t for c in coins if c in mids for t in demo.close_manual(chosen, c, mids[c])]
            if not closed:
                return (f"В демо сметката „{name}“ нямате отворена позиция"
                        + (f" в {NAMES[coins[0]]}." if len(coins) == 1 else "."))
            demo.save(book)
        return texts.demo_closed(name, closed, chosen)
    try:
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
    """Спира истинската търговия (бутона REAL TRADE): Орион не отваря истински сделки, докато сър не я пусне."""
    return modes.set_real(False)


@orion_tool
def resume_trading() -> str:
    """Пуска истинската търговия (бутона REAL TRADE) — всяка сделка пак чака „Одобри“."""
    return modes.set_real(True)


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


# --- Demo accounts, the simulation, the buttons ------------------------------------------------------
@orion_tool
def create_demo_account(balance: float, name: str = "", currency: str = "USD", risk_pct: float = 2.0,
                        all_signals: bool = False) -> str:
    """Прави демо сметка с измислени пари (напр. 1000 долара), на която Орион търгува сам по истинските цени,
    без истински пари. Може да има няколко, с имена и свой риск.

    Args:
        balance: Началните пари, напр. 1000.
        name: Име на сметката (празно — „демо 1“, „демо 2“…).
        currency: Валутата на сумата: USD (по подразбиране), лева или евро.
        risk_pct: Колко % от сметката рискува на сделка (по подразбиране 2).
        all_signals: True — търгува и стратегиите, които не са минали проверката.
    """
    try:
        usd = demo.to_usd(float(balance), currency)
        made = demo.create(name, usd, float(risk_pct), bool(all_signals))
    except ValueError as e:
        return str(e)
    except OSError:
        return RATE_DOWN
    text = texts.demo_created(made, usd, float(risk_pct), bool(all_signals), float(balance), currency)
    if not settings.demo_on():
        text += " Включете DEMO TEST (бутона долу или „включи демо теста“), за да започна да търгувам на нея."
    return text


@orion_tool
def demo_status() -> str:
    """Как вървят демо сметките: баланс, печалба или загуба в %, сделки и отворени позиции."""
    book = demo.load()
    if not book["accounts"]:
        return NO_DEMO
    try:
        mids = _mids()
    except OSError:
        mids = {}
    return texts.demo_status(book, mids, settings.demo_on())


@orion_tool
def delete_demo_account(name: str) -> str:
    """Изтрива демо сметка.

    Args:
        name: Името на сметката, напр. "демо 1".
    """
    try:
        return f"Изтрих демо сметката „{demo.delete(name)}“."
    except ValueError as e:
        return str(e)


@orion_tool
def reset_demo_account(name: str = "") -> str:
    """Започва демо сметка отначало — същите пари и риск, без сделките (празно — всички демо сметки).

    Args:
        name: Името на сметката (празно — всички).
    """
    try:
        names = demo.reset(name)
    except ValueError as e:
        return str(e)
    return "Започнах отначало: " + ", ".join(f"„{n}“" for n in names) + "."


@orion_tool
def choose_demo_account(name: str) -> str:
    """Избира демо сметката, в която отиват командите „отвори…“ и „затвори…“.

    Args:
        name: Името на сметката.
    """
    try:
        return f"Избрах демо сметката „{demo.choose(name)}“."
    except ValueError as e:
        return str(e)


@orion_tool
def simulate_history(balance: float, days: int = 365, currency: str = "USD", risk_pct: float = 2.0,
                     all_signals: bool = False) -> str:
    """Симулация: какво би станало с дадена сума, ако Орион беше търгувал по стратегиите си през последните дни —
    краен баланс, най-голямо падане, най-добър и най-лош месец.

    Args:
        balance: Началните пари, напр. 1000.
        days: За колко дни назад (365 — година).
        currency: USD (по подразбиране), лева или евро.
        risk_pct: Риск на сделка в % (по подразбиране 2).
        all_signals: True — и стратегиите, които не са минали проверката.
    """
    try:
        usd = demo.to_usd(float(balance), currency)
    except ValueError as e:
        return str(e)
    except OSError:
        return RATE_DOWN
    report = backtest.load()
    if report is None and not all_signals:
        backtest.refresh_async()
        return texts.NO_REPORT
    try:
        result = simulate.run(usd, int(days), float(risk_pct), bool(all_signals), report)
    except OSError:
        return texts.NO_DATA
    return texts.simulation(result, float(risk_pct), bool(all_signals))


@orion_tool
def set_demo_test(on: bool) -> str:
    """Включва или спира DEMO TEST — Орион търгува сам на демо сметките, без истински пари.

    Args:
        on: True — включи, False — спри.
    """
    return modes.set_demo(bool(on))


@orion_tool
def set_real_trading(on: bool) -> str:
    """Включва или спира REAL TRADE — истинската сметка в Hyperliquid (всяка сделка с „Одобри“).

    Args:
        on: True — включи, False — спри.
    """
    return modes.set_real(bool(on))
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_trading_demo_skills.py tests/test_trading_skills.py -q -p no:cacheprovider`
Expected: PASS

Run: `python -m pytest -q -p no:cacheprovider`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add skills/crypto_trading_skills.py orion/trading/exchange.py tests/test_trading_demo_skills.py tests/test_trading_skills.py
git commit -m "Skills: demo accounts, simulation, the two buttons; open/close routed to the demo or the real account"
```

---
### Task 5: The watch runs the demo, test mode goes back to skills, the app wires the buttons

**Files:**
- Replace: `orion/trading/watcher.py`, `tests/test_trading_watcher.py`, `tests/test_self_test_trading.py` (whole files)
- Restore + modify: `orion/self_test.py` (back to the version before the trading stage, keeping the sandbox block)
- Modify: `app.py`, `tests/test_app_trading.py` (one test appended)

**Interfaces:**
- Consumes: `demo.load/save/step`, `practice.step/testnet_due/mark_testnet`, `lab.due/search/start`, `modes.set_demo/set_real`, `settings.demo_on/enabled`
- Produces: hud `("setTrading", {"network": str|None, "positions": [...], "demo": [{"name", "pct"}]} | None)`; `HudApi.set_demo_mode(enabled)`, `HudApi.set_real_trading(enabled)`; start-up dict keys `demoMode`, `realTrading`; `trading.on_switch` set by app.py to `hud("setSwitch", name, on)`

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_trading_watcher.py` with:

```python
import threading
from datetime import datetime

import pytest

from orion.trading import backtest, data, demo, exchange, journal, lab, market, practice, risk, settings, signals, watcher
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
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "demo.json")
    monkeypatch.setattr(practice, "PRACTICE", tmp_path / "practice.json")
    monkeypatch.setattr(lab, "LAB", tmp_path / "lab.json")
    settings.set_enabled(True)                       # REAL TRADE on — the real alerts are tested here
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
    w.scan()
    world["BTC"] = [sig(2)]
    w.scan()
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
    assert journal.record(days=1)["open"] == 2


def test_at_night_only_the_journal(world):
    w, said, hud = make(hour=2)
    world["BTC"] = [sig(1)]
    w.scan()
    assert said == [] and hud[0][0] == "addLog"


def test_real_alerts_need_real_trade(world):
    settings.set_enabled(False)
    w, said, hud = make()
    world["BTC"] = [sig(1)]
    w.scan()
    assert said == [] and hud == [] and journal.record(days=1)["open"] == 1


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
        {"coin": "BTC", "side": "long", "pnl_usd": 5.0, "pnl_pct": 1.0}], "demo": []},)) in hud
    assert [s for s in said if "Етериум" in s] == ["Сър, позицията в Етериум се затвори на 1 901 — +5.00 долара."]
    assert sum("48 часа" in s for s in said) == 1
    w.positions()
    assert sum("48 часа" in s for s in said) == 1
    assert sum("Етериум" in s for s in said) == 1


def test_no_key_and_no_demo_hides_the_chip(world):
    w, said, hud = make()
    w.positions()
    assert hud == [("setTrading", (None,))]


def test_the_chip_shows_the_demo_accounts_without_a_key(world):
    settings.set_demo(True)
    demo.create("", 1000)
    w, said, hud = make()
    w.positions()
    assert hud == [("setTrading", ({"network": None, "positions": [], "demo": [{"name": "демо 1", "pct": 0.0}]},))]


def test_demo_and_practice_run_only_with_demo_test_on(world, monkeypatch):
    calls = []
    monkeypatch.setattr(demo, "step", lambda book, prepared, report: (
        calls.append(("demo", sorted(prepared))), ["DEMO демо 1: отворих лонг на биткойн."])[1])
    monkeypatch.setattr(practice, "step", lambda prepared: calls.append(("practice", sorted(prepared))))
    w, said, hud = make()
    w.scan()
    assert calls == []
    settings.set_demo(True)
    w.scan()
    assert calls == [("demo", ["BTC", "ETH", "SOL"]), ("practice", ["BTC", "ETH", "SOL"])]
    assert ("addLog", ("trading", "DEMO демо 1: отворих лонг на биткойн.")) in hud and said == []


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
    assert calls == []
    w.clock.now += 15 * 60
    w.tick()
    assert calls == ["scan", "positions"]


def test_the_lab_search_and_the_testnet_check_run_without_the_lock(world, monkeypatch):
    settings.set_demo(True)
    w, said, hud = make()
    monkeypatch.setattr(w, "scan", lambda: None)
    monkeypatch.setattr(w, "positions", lambda: None)
    monkeypatch.setattr(journal, "resolve", lambda bars_for=None: None)
    held, marked = [], []
    monkeypatch.setattr(lab, "due", lambda: "breakout")
    monkeypatch.setattr(market, "history", lambda coin, params=None: coin)
    monkeypatch.setattr(lab, "search", lambda strategy, markets: (held.append(("search", w.lock.locked())), None)[1])
    monkeypatch.setattr(lab, "start", lambda strategy, found, log=print: (
        held.append(("start", w.lock.locked())), "пробвам нови числа")[1])
    monkeypatch.setattr(practice, "testnet_due", lambda: True)
    monkeypatch.setattr(practice, "mark_testnet", lambda: marked.append(w.lock.locked()))
    monkeypatch.setattr(exchange, "testnet_check", lambda: (held.append(("testnet", w.lock.locked())),
                                                            "Проверката мина.")[1])
    w.tick()
    assert held == [("search", False), ("start", True), ("testnet", False)] and marked == [True]
    assert ("addLog", ("trading", "Лаборатория: пробвам нови числа.")) in hud
    assert ("addLog", ("trading", "Проверката мина.")) in hud
```

Replace `tests/test_self_test_trading.py` with:

```python
from types import SimpleNamespace

from orion import self_test
from orion.trading import exchange


def test_the_sandbox_blocks_the_exchange():
    assert not exchange.blocked
    with self_test.Sandbox():
        assert exchange.blocked
    assert not exchange.blocked


def test_test_mode_checks_skills_and_understanding_every_round_without_trading(monkeypatch):
    tester = self_test.SelfTester(SimpleNamespace())
    calls = []
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
    assert [c for c in calls if c[0] == "asks"] == [("asks", n) for n in range(1, 5)]
    assert [c for c in calls if c[0] == "skills"] == [("skills", 1), ("skills", 4)]
    assert not hasattr(tester, "_practice") and not hasattr(self_test.Report(1), "trading")
```

Append to `tests/test_app_trading.py`:

```python


def test_the_two_trading_buttons(monkeypatch, tmp_path):
    from orion.trading import demo
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "s.json")
    monkeypatch.setattr(demo, "DEMO_FILE", tmp_path / "d.json")
    said = []
    api = app.HudApi(bare_app(said, []))
    api.set_demo_mode(True)
    assert settings.demo_on() and "„демо 1“" in said[-1]
    api.set_real_trading(False)
    assert not settings.enabled() and "Спрях истинската търговия" in said[-1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trading_watcher.py tests/test_self_test_trading.py tests/test_app_trading.py -q -p no:cacheprovider`
Expected: FAIL — the chip payload has no `"demo"`, real alerts ignore REAL TRADE, `demo.step` is never called, the lab test fails, test mode still has `_practice`, `HudApi` has no `set_demo_mode`

- [ ] **Step 3: Replace `orion/trading/watcher.py` with:**

```python
"""
The background watch (own thread, started by app.py). Every 15 minutes it fetches the three coins once and
uses them for everything: each new signal goes into the journal; with REAL TRADE on, a strong signal of a
checked strategy is announced (voice 08:00–23:00, journal always); with DEMO TEST on, the demo accounts and
the practice account trade by themselves (journal only). With a key connected it checks the real account
(every minute while positions are open, else every 5): closed trades and the 48-hour time stop. The top-bar
chip shows the real positions and the demo accounts. It holds test mode's sandbox lock while it touches
files; the lab's minutes of CPU and the testnet order check run without it.
"""
import time
from datetime import datetime

from . import COINS, NAMES, backtest, data, demo, exchange, journal, lab, market, practice, settings, signals, texts

SCAN_EVERY = 15 * 60
RESOLVE_EVERY = 60 * 60
REFRESH_RETRY = 30 * 60
LAB_EVERY = 60 * 60
REPEAT_HOURS = 6


class Watcher:
    def __init__(self, say, hud, lock, clock=time.time):
        self.say, self.hud, self.lock, self.clock = say, hud, lock, clock
        self.last_scan = self.last_positions = self.last_resolve = self.last_refresh = self.last_lab = -1e18
        self.announced: dict[tuple[str, str], float] = {}
        self.fills_from = int(clock() * 1000)
        self.time_stop_told: set[str] = set()

    def run(self) -> None:
        while True:
            self.tick()
            time.sleep(5)

    def _safe(self, job, *args):
        try:
            return job(*args)
        except Exception as e:  # noqa: BLE001 — the watch must never stop Orion
            print(f"[Trading] {getattr(job, '__name__', 'job')}: {type(e).__name__}: {e}")
            return None

    def tick(self) -> None:
        now = self.clock()
        strategy, testnet = None, False
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
            if now - self.last_lab >= LAB_EVERY and self._safe(settings.demo_on):
                self.last_lab = now
                strategy = self._safe(lab.due)
                if self._safe(practice.testnet_due):
                    self._safe(practice.mark_testnet)
                    testnet = True
        if strategy:
            self._safe(self.lab_search, strategy)
        if testnet:
            self._safe(self.testnet)
        if now - self.last_refresh >= REFRESH_RETRY and backtest.stale():
            self.last_refresh = now
            backtest.refresh_async(self.lock)

    # --- Signals, real alerts, demo trades --------------------------------------------------------
    def scan(self) -> None:
        report = backtest.load()
        options = settings.load()
        prepared = {coin: market.live(coin) for coin in COINS}
        for p in prepared.values():
            for s in signals.latest(p):
                if (journal.add_signal(s, "watch") and options["enabled"]
                        and self._worth(s, report, options["announce_strength"])):
                    self.announce(texts.signal_alert(s, report))
        if options["demo"]:
            self.demo_step(prepared, report)
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

    def demo_step(self, prepared: dict, report: dict | None) -> None:
        """DEMO TEST: the demo accounts and the practice account trade by themselves — journal only."""
        with demo._lock:
            book = demo.load()
            lines = demo.step(book, prepared, report)
            demo.save(book)
        for line in lines:
            self.hud("addLog", "trading", line)
        practice.step(prepared)

    def lab_search(self, strategy: str) -> None:
        found = lab.search(strategy, {coin: market.history(coin) for coin in COINS})   # minutes of CPU, no lock
        with self.lock:
            note = lab.start(strategy, found)
        if note:
            self.hud("addLog", "trading", f"Лаборатория: {note}.")

    def testnet(self) -> None:
        self.hud("addLog", "trading", exchange.testnet_check())

    # --- The real account and the chip -----------------------------------------------------------
    def chip(self, network: str | None, state) -> None:
        payload = {"network": network, "positions": [], "demo": []}
        if state:
            payload["positions"] = [
                {"coin": coin, "side": p["side"], "pnl_usd": round(p["pnl"], 2),
                 "pnl_pct": round(p["pnl"] / p["value"] * 100, 2) if p["value"] else 0.0}
                for coin, p in state.positions.items()]
        if settings.demo_on():
            payload["demo"] = [{"name": name, "pct": round((a["balance"] / a["start"] - 1) * 100, 2)}
                               for name, a in demo.load()["accounts"].items()]
        self.hud("setTrading", payload if network or payload["demo"] else None)

    def positions(self) -> None:
        network = settings.network()
        state = exchange.account_state(network)[0] if settings.account(network) else None
        self.chip(network if state else None, state)
        if state is None:
            return
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

- [ ] **Step 4: Test mode without the trading stage**

Run: `git show c40e770:orion/self_test.py > orion/self_test.py`
(This is test mode exactly as it was before the first plan's Task 14 added the trading stage.)

Then in `orion/self_test.py` find:

```python
        self._set(confirm, "handler", lambda *args, **kwargs: False)
```

and add right after it:

```python
        from .trading import exchange as trading_exchange
        self._set(trading_exchange, "blocked", True)  # skills under test never reach the exchange
```

- [ ] **Step 5: Wire the buttons in `app.py`**

Find:

```python
from orion.trading import settings as trading_settings  # noqa: E402
```

and add right after it:

```python
from orion.trading import modes as trading_modes  # noqa: E402
```

Find:

```python
        return {"muted": self.muted, "alwaysListen": self.always_listen, "testMode": self.tester.running,
                "wakeWord": config.WAKE_WORDS[0], "maximized": self.start_maximized}
```

and replace with:

```python
        return {"muted": self.muted, "alwaysListen": self.always_listen, "testMode": self.tester.running,
                "demoMode": trading_settings.demo_on(), "realTrading": trading_settings.enabled(),
                "wakeWord": config.WAKE_WORDS[0], "maximized": self.start_maximized}
```

Find:

```python
        trading.show_key_dialog = lambda network: self.hud("showKeyDialog", {"network": network})
```

and add right after it:

```python
        trading.on_switch = lambda name, on: self.hud("setSwitch", name, on)
```

Find:

```python
        self._app.say(message)
        return {"ok": True, "message": message}
```

and add right after it:

```python

    def set_demo_mode(self, enabled: bool):
        """DEMO TEST — Orion trades the demo accounts by itself."""
        self._app.say(trading_modes.set_demo(bool(enabled)))

    def set_real_trading(self, enabled: bool):
        """REAL TRADE — the real Hyperliquid account (every trade with approval)."""
        self._app.say(trading_modes.set_real(bool(enabled)))
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_trading_watcher.py tests/test_self_test_trading.py tests/test_app_trading.py -q -p no:cacheprovider`
Expected: PASS

Run: `python -m pytest -q -p no:cacheprovider`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add orion/trading/watcher.py orion/self_test.py app.py tests/test_trading_watcher.py tests/test_self_test_trading.py tests/test_app_trading.py
git commit -m "Watch: demo and practice with DEMO TEST, real alerts with REAL TRADE, lab outside the lock; test mode back to skills"
```

---

### Task 6: Phrases — demo, simulation, the buttons; router, nudge, persona, test-mode asks

**Files:**
- Modify: `orion/reflexes.py`, `orion/router.py`, `orion/brain.py`, `config.py`, `orion/self_test_cases.py`
- Test: `tests/test_trading_demo_reflexes.py`

**Interfaces:**
- Consumes: the skill names of Task 4
- Produces: `reflexes._demo_command(plain) -> Reflex | None` (called first in `_trading_command`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_trading_demo_reflexes.py`:

```python
import json

import pytest

from orion import brain, reflexes, router


@pytest.mark.parametrize("text, tool, args", [
    ("искам да тренираш сметка която е с 1000 долара и да направиш 10 000 лв чисто симулационно",
     "create_demo_account", {"balance": 1000.0, "currency": "долара"}),
    ("Направи демо сметка „предпазлива“ с 500 долара и 1 % риск", "create_demo_account",
     {"balance": 500.0, "currency": "долара", "name": "предпазлива", "risk_pct": 1.0}),
    ("Направи демо сметка с 10 000 лева с всички сигнали", "create_demo_account",
     {"balance": 10000.0, "currency": "лева", "all_signals": True}),
    ("Симулирай 1000 долара за последната година", "simulate_history",
     {"balance": 1000.0, "currency": "долара", "days": 365}),
    ("Симулирай 500 долара за 6 месеца с 1% риск", "simulate_history",
     {"balance": 500.0, "currency": "долара", "days": 180, "risk_pct": 1.0}),
    ("Как върви демото?", "demo_status", {}),
    ("Покажи демо сметките", "demo_status", {}),
    ("Изтрий демо сметката „предпазлива“", "delete_demo_account", {"name": "предпазлива"}),
    ("Започни демото отначало", "reset_demo_account", {"name": ""}),
    ("Избери демо сметката „смел“", "choose_demo_account", {"name": "смел"}),
    ("Включи демо теста", "set_demo_test", {"on": True}),
    ("Спри демо теста", "set_demo_test", {"on": False}),
    ("Включи реал трейд", "set_real_trading", {"on": True}),
    ("Спри реал трейд", "set_real_trading", {"on": False}),
    ("Отвори лонг на биткойн в демото", "open_trade", {"coin": "биткойн в демото", "side": "long", "account": "демо"}),
    ("Затвори етериума в демото", "close_trade", {"coin": "етериума в демото", "account": "демо"}),
])
def test_demo_phrases_are_reflexes(text, tool, args):
    reflex = reflexes.respond(text)
    assert reflex is not None and reflex.tool == tool and reflex.arguments == args


def test_plain_trading_phrases_are_unchanged():
    assert reflexes.respond("Отвори лонг на биткойн").arguments == {"coin": "биткойн", "side": "long"}


def test_the_router_and_the_nudge_know_the_demo():
    assert "skills.crypto_trading_skills" not in router.excluded_modules("Искам симулационна сметка")
    name, arguments = brain.Brain._default_call("Можеш ли да тренираш на демо сметка?")
    assert name == "demo_status" and json.loads(arguments) == {}
    assert {"demo_status", "simulate_history"} <= brain.READ_ONLY_TOOLS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trading_demo_reflexes.py -q -p no:cacheprovider`
Expected: FAIL — the demo phrases return None or other reflexes

- [ ] **Step 3: The reflexes**

In `orion/reflexes.py`, find:

```python
def _trading_command(plain: str) -> Reflex | None:
```

and add directly ABOVE it:

```python
# Demo accounts, the history simulation and the DEMO TEST / REAL TRADE buttons.
_AMOUNT_RE = re.compile(r"(?P<amount>\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*"
                        r"(?P<cur>долара|долар|\$|usd|лева|лв\.?|лев|евро|eur|€)", re.IGNORECASE)
_RISK_RE = re.compile(r"(?P<risk>\d+(?:[.,]\d+)?)\s*%\s*риск|риск\w*\s+(?:от\s+)?(?P<risk2>\d+(?:[.,]\d+)?)\s*%",
                      re.IGNORECASE)
_DAYS_RE = re.compile(r"(?P<n>\d+)\s*(?P<unit>дни|ден|месеца|месец|години|година)|"
                      r"(?P<word>годината|година|месеца|месец|седмицата|седмица)", re.IGNORECASE)
_QUOTED_RE = re.compile(r"[„\"“](?P<name>[^„“\"]+)[“\"]")
_DEMO_WORDS_RE = re.compile(r"демо|симулацион|тренировъчн|виртуалн|тренир", re.IGNORECASE)
_CREATE_WORDS_RE = re.compile(r"\b(?:направи|създай|отвори|започни|искам|тренирай|тренираш|заведи)\b", re.IGNORECASE)
_SWITCH_RE = re.compile(r"(?P<verb>включи|пусни|стартирай|изключи|спри)\s+(?P<what>демо\s*теста|демо\s*тест|"
                        r"демо\s*режима|демо\s*търговията|демото|реал\s*трейд\w*|real\s*trade|истинската търговия|"
                        r"реалната търговия)", re.IGNORECASE)
_DEMO_DELETE_RE = re.compile(r"(?:изтрий|махни|премахни)\s+(?:демо\s+)?сметк\w*\s*(?P<name>.*)", re.IGNORECASE)
_DEMO_RESET_RE = re.compile(r"(?:започни|рестартирай|нулирай|почни)\s+(?:демо\s+сметк\w*|демото|демо)(?P<name>.*?)\s*"
                            r"(?:отначало|наново|от нулата)", re.IGNORECASE)
_DEMO_CHOOSE_RE = re.compile(r"(?:избери|ползвай|използвай)\s+(?:демо\s+)?сметк\w*\s*(?P<name>.+)", re.IGNORECASE)
_DEMO_STATUS_RE = re.compile(r"как\s+(?:върв\w*|е|са|се справя\w*|стои|стоят)|какво става|покажи|резултат|баланс",
                             re.IGNORECASE)


def _money(match: re.Match) -> float:
    return float(match["amount"].replace(" ", "").replace(" ", "").replace(",", "."))


def _days(text: str) -> int:
    match = _DAYS_RE.search(text)
    if not match:
        return 365
    if match["n"]:
        unit = match["unit"].lower()
        return int(match["n"]) * (365 if unit.startswith("годин") else 30 if unit.startswith("месец") else 1)
    word = match["word"].lower()
    return 365 if word.startswith("годин") else 30 if word.startswith("месец") else 7


def _demo_command(plain: str) -> Reflex | None:
    """Demo accounts, the simulation and the two trading buttons — Orion never answers „не мога“ to these."""
    lower = plain.lower()
    match = _SWITCH_RE.search(plain)
    if match:
        on = match["verb"].lower() in ("включи", "пусни", "стартирай")
        tool = "set_demo_test" if "демо" in match["what"].lower() else "set_real_trading"
        return Reflex(tool=tool, arguments={"on": on})
    amount = _AMOUNT_RE.search(plain)
    extra = {}
    risk = _RISK_RE.search(plain)
    if risk:
        extra["risk_pct"] = float((risk["risk"] or risk["risk2"]).replace(",", "."))
    if "всички сигнали" in lower:
        extra["all_signals"] = True
    if amount and "сметк" in lower and _DEMO_WORDS_RE.search(plain) and _CREATE_WORDS_RE.search(plain):
        name = _QUOTED_RE.search(plain)
        if name:
            extra["name"] = name["name"].strip()
        return Reflex(tool="create_demo_account", arguments={"balance": _money(amount), "currency": amount["cur"], **extra})
    if amount and re.search(r"симулир|симулаци", lower):
        return Reflex(tool="simulate_history", arguments={"balance": _money(amount), "currency": amount["cur"],
                                                          "days": _days(plain[amount.end():]), **extra})
    if "демо" not in lower:
        return None
    for pattern, tool in ((_DEMO_DELETE_RE, "delete_demo_account"), (_DEMO_CHOOSE_RE, "choose_demo_account")):
        match = pattern.fullmatch(plain)
        if match and match["name"].strip():
            return Reflex(tool=tool, arguments={"name": match["name"].strip().strip("„“\"")})
    match = _DEMO_RESET_RE.fullmatch(plain)
    if match:
        return Reflex(tool="reset_demo_account", arguments={"name": match["name"].strip().strip("„“\"")})
    if _DEMO_STATUS_RE.search(plain):
        return Reflex(tool="demo_status", arguments={})
    return None


```

In `_trading_command`, find:

```python
    from .trading import coins_in, exchange
```

and add right after it:

```python
    demo = _demo_command(plain)
    if demo:
        return demo
```

Find:

```python
    match = _TRADE_OPEN_RE.fullmatch(plain)
    if match and coins_in(match["coin"]):
        side = "long" if match["side"].lower() in ("лонг", "лонк", "long") else "short"
        return Reflex(tool="open_trade", arguments={"coin": match["coin"].strip(), "side": side})
    match = _TRADE_CLOSE_RE.fullmatch(plain)
    if match and coins_in(match["coin"]):
        return Reflex(tool="close_trade", arguments={"coin": match["coin"].strip()})
    return None
```

and replace with:

```python
    match = _TRADE_OPEN_RE.fullmatch(plain)
    if match and coins_in(match["coin"]):
        side = "long" if match["side"].lower() in ("лонг", "лонк", "long") else "short"
        arguments = {"coin": match["coin"].strip(), "side": side}
        if "демо" in match["coin"].lower():
            arguments["account"] = "демо"
        return Reflex(tool="open_trade", arguments=arguments)
    match = _TRADE_CLOSE_RE.fullmatch(plain)
    if match and coins_in(match["coin"]):
        arguments = {"coin": match["coin"].strip()}
        if "демо" in match["coin"].lower():
            arguments["account"] = "демо"
        return Reflex(tool="close_trade", arguments=arguments)
    return None
```

- [ ] **Step 4: Router, nudge, persona, asks**

In `orion/router.py`, find:

```python
        r"тестовата мрежа|истински пари", re.IGNORECASE),
```

and replace with:

```python
        r"тестовата мрежа|истински пари|демо|симулац|симулир|сметк|тренир|виртуал|реал трейд|real trade",
        re.IGNORECASE),
```

In `orion/brain.py`, find:

```python
     "crypto_forecast, crypto_signals, open_trade или close_trade", ("crypto_forecast", {"coin": USER_TEXT})),
```

and add right after it:

```python
    # Demo accounts and the simulation — the model used to say it cannot manage any account.
    (re.compile(r"демо|симулаци|симулир|тренировъчн\w*\s+сметк|виртуалн\w*\s+сметк|тренира\w*.*сметк", re.IGNORECASE),
     "create_demo_account, demo_status, simulate_history или set_demo_test", ("demo_status", {})),
```

Find:

```python
    "crypto_forecast", "crypto_signals", "strategy_report", "forecast_record", "trading_positions", "trading_account",
```

and add right after it:

```python
    "demo_status", "simulate_history",
```

In `config.py`, find the line that starts with `- Крипто прогнози и търговия (биткойн, етериум, солана в Hyperliquid):` and add this line right after it:

```
- Демо сметки и симулации: демо сметка с измислени пари — create_demo_account (напр. 1000 долара; може няколко, с имена), как вървят — demo_status, изтриване, начало отначало и избор — delete_demo_account, reset_demo_account, choose_demo_account; какво би станало в миналото — simulate_history; бутоните DEMO TEST и REAL TRADE — set_demo_test и set_real_trading. Никога не казвай, че не можеш да търгуваш или да управляваш сметка: на демо сметките търгуваш сам, а за истински пари сър свързва Hyperliquid и включва REAL TRADE.
```

In `orion/self_test_cases.py`, find:

```python
    A("Какви позиции имам?", ("trading_positions", "trading_account")),
```

and add right after it:

```python
    A("Направи демо сметка с 1000 долара", ("create_demo_account",)),
    A("Как върви демото?", ("demo_status",)),
    A("Симулирай 1000 долара за последната година", ("simulate_history",)),
    A("Включи демо теста", ("set_demo_test",)),
```

Find:

```python
    C("crypto_forecast", {"coin": "биткойн"}, r"(?i)биткойн"), C("crypto_signals", {}, r"(?i)етериум"),
```

and add right after it:

```python
    C("demo_status", {}, r"демо сметка"), C("simulate_history", {"balance": 1000, "days": 30}, r"(?i)проверката|симулац"),
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_trading_demo_reflexes.py tests/test_trading_reflexes.py -q -p no:cacheprovider`
Expected: PASS

Run: `python -m pytest -q -p no:cacheprovider`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add orion/reflexes.py orion/router.py orion/brain.py config.py orion/self_test_cases.py tests/test_trading_demo_reflexes.py
git commit -m "Phrases for demo accounts, the simulation and the two buttons; router, nudge, persona, asks"
```

---
### Task 7: The window — two switches and the demo chip

**Files:**
- Modify: `web/src/store.js`, `web/src/actions.js`, `web/src/bridge.js`, `web/src/components/Console.jsx`, `web/src/styles.css`
- Test: `web/src/components/Modes.test.jsx` (new)
- Build output: `ui/`

**Interfaces:**
- Consumes: `pywebview.api.set_demo_mode(bool)`, `set_real_trading(bool)`; start-up `demoMode`, `realTrading`; hud `setSwitch('demo'|'real', bool)`, `setTrading({network, positions, demo})`
- Produces: `store.switches.demo`, `store.switches.real`

- [ ] **Step 1: Write the failing test**

Create `web/src/components/Modes.test.jsx`:

```jsx
import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { hud } from '../bridge.js';
import { store } from '../store.js';
import { Console } from './Console.jsx';
import { Jobs } from './Jobs.jsx';

describe('the trading buttons', () => {
  afterEach(() => {
    cleanup();
    store.set({ trading: null, switches: { wake: false, voice: true, test: false, demo: false, real: false } });
    delete window.pywebview;
  });

  it('the console has Demo test and Real trade next to Test mode', () => {
    const { getByLabelText } = render(<Console />);
    expect(getByLabelText('Test mode')).toBeTruthy();
    expect(getByLabelText('Demo test')).toBeTruthy();
    expect(getByLabelText('Real trade')).toBeTruthy();
  });

  it('switching them tells Python', () => {
    const demo = vi.fn();
    const real = vi.fn();
    window.pywebview = { api: { set_demo_mode: demo, set_real_trading: real } };
    const { getByLabelText } = render(<Console />);
    fireEvent.click(getByLabelText('Demo test'));
    fireEvent.click(getByLabelText('Real trade'));
    expect(demo).toHaveBeenCalledWith(true);
    expect(real).toHaveBeenCalledWith(true);
  });

  it('Python can move them', () => {
    hud.setSwitch('demo', true);
    hud.setSwitch('real', true);
    expect(store.get().switches.demo).toBe(true);
    expect(store.get().switches.real).toBe(true);
  });

  it('the chip shows the demo accounts even without a key', () => {
    hud.setTrading({ network: null, positions: [], demo: [{ name: 'демо 1', pct: 3.24 }, { name: 'смел', pct: -0.4 }] });
    const { container } = render(<Jobs />);
    expect(container.textContent).toContain('trading · DEMO демо 1 +3.2% · DEMO смел -0.4%');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/components/Modes.test.jsx`
Expected: FAIL — no `Demo test` / `Real trade` labels; `setSwitch('demo')` ignored; the chip has no DEMO part

- [ ] **Step 3: Implement**

In `web/src/store.js`, find:

```js
  switches: { wake: false, voice: true, test: false },
```

and replace with:

```js
  switches: { wake: false, voice: true, test: false, demo: false, real: false },
```

In `web/src/actions.js`, find:

```js
  if (name === 'test') api()?.set_test_mode(checked);
```

and add right after it:

```js
  if (name === 'demo') api()?.set_demo_mode(checked);
  if (name === 'real') api()?.set_real_trading(checked);
```

In `web/src/bridge.js`, find:

```js
    if (!['wake', 'voice', 'test'].includes(name)) return;
```

and replace with:

```js
    if (!['wake', 'voice', 'test', 'demo', 'real'].includes(name)) return;
```

Find:

```js
  hud.setSwitch('test', settings.testMode);
```

and add right after it:

```js
  hud.setSwitch('demo', Boolean(settings.demoMode));
  hud.setSwitch('real', Boolean(settings.realTrading));
```

Find the whole `setTrading(data) {` method:

```js
  setTrading(data) {
    if (!data) {
      store.set({ trading: null });
      return;
    }
    const parts = data.positions.map((p) => `${p.coin} ${p.side.toUpperCase()} ${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct.toFixed(1)}%`);
    if (data.network === 'testnet') parts.unshift('TESTNET');
    store.set({ trading: parts.length ? `trading · ${parts.join(' · ')}` : null });
  },
```

and replace with:

```js
  setTrading(data) {
    if (!data) {
      store.set({ trading: null });
      return;
    }
    const pct = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
    const parts = data.positions.map((p) => `${p.coin} ${p.side.toUpperCase()} ${pct(p.pnl_pct)}`);
    if (data.network === 'testnet') parts.unshift('TESTNET');
    for (const account of data.demo || []) parts.push(`DEMO ${account.name} ${pct(account.pct)}`);
    store.set({ trading: parts.length ? `trading · ${parts.join(' · ')}` : null });
  },
```

In `web/src/components/Console.jsx`, find:

```jsx
  { name: 'test', label: 'Test mode', className: 'switch switch--test',
    title: 'Orion checks its own skills and whether it understands you, and fixes its mistakes. Tests pause while you talk to it.' },
```

and add right after it:

```jsx
  { name: 'demo', label: 'Demo test', className: 'switch switch--demo',
    title: 'Orion trades the demo accounts by itself — virtual money on live prices, never a real order' },
  { name: 'real', label: 'Real trade', className: 'switch switch--real',
    title: 'The real Hyperliquid account: forecasts when you ask, every trade only after you approve it' },
```

In `web/src/styles.css`, find:

```css
.switch--test input:checked::before { background: var(--test); }
```

and add right after it:

```css
.switch--demo input:checked { background: rgba(127, 219, 255, 0.16); border-color: var(--holo); }
.switch--demo input:checked::before { background: var(--holo); }
.switch--real input:checked { background: rgba(255, 90, 78, 0.16); border-color: var(--alert); }
.switch--real input:checked::before { background: var(--alert); }
```

- [ ] **Step 4: Run the web tests and build**

Run: `cd web && npx vitest run`
Expected: PASS (all, including Trading.test.jsx's chip test)

Run: `cd web && npm run build`
Expected: `✓ built`

Run (PowerShell): `python web/e2e/run.py`
Expected: `passed 37, failed 0`

- [ ] **Step 5: Look at it**

Take a headless Edge screenshot of the built window (same stub as `web/e2e`) with `hud.setSwitch('demo', true)` and `hud.setTrading({network: null, positions: [], demo: [{name: 'демо 1', pct: 1.5}]})`: the five switches fit in the bottom bar at 1280×800 without cutting the input box, and the chip reads `TRADING · DEMO ДЕМО 1 +1.5%`. If the switches wrap or cut the input, fix the CSS (`.switches { gap: 14px; }`) and record a ruling.

- [ ] **Step 6: Commit**

```bash
git add web/src ui
git commit -m "Window: Demo test and Real trade switches, demo accounts in the trading chip"
```

---

### Task 8: Real data, README, final check

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Every test**

Run: `python -m pytest -q -p no:cacheprovider` → PASS (all)
Run: `cd web && npx vitest run` → PASS (all)

- [ ] **Step 2: The simulation on real data**

Run:

```bash
python -c "import config, sys; from orion.tools import registry; registry.load_skills(config.SKILLS_DIR); m = sys.modules['skills.crypto_trading_skills']; print(m.simulate_history(1000)); print(m.simulate_history(1000, risk_pct=1)); print(m.simulate_history(1000, all_signals=True))"
```

Expected: three Bulgarian sentences built from the cached history and `memory/trading_stats.json` (checked strategies: breakout on BTC and ETH at the time of writing). Save them for sir word for word — whatever they say.

- [ ] **Step 3: README**

In `README.md`, find the paragraph that starts with `**Test mode** practises trading every round:` (three lines, ending with `checks that stops and targets are placed.`) and replace the whole paragraph with:

```markdown
**Three buttons** in the bottom bar. **Test mode** checks Orion's own skills and understanding. **Demo test**
lets Orion trade the demo accounts by itself — virtual money on live prices („направи демо сметка с 1000
долара“, „как върви демото“, „започни демото отначало“) — and runs the strategy lab (other numbers promoted
only after beating the current ones on unseen history AND in 20 practice trades) and a daily minimum-size
testnet order check. **Real trade** is the real Hyperliquid account: forecasts and advice when you ask, every
trade only after „Одобри“; off means no real orders. „Симулирай 1000 долара за последната година“ replays the
checked strategies on history with compounding (final balance, worst drawdown, best and worst month).
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "README: the three buttons, demo accounts and the simulation"
```
