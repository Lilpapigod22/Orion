# Autonomous real trading through Phantom Perps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While REAL TRADE is on, Orion opens and closes real Hyperliquid (Phantom Perps) trades by itself on the checked strategies, within hard limits, with a −40 % account stop — and Trust Wallet disappears from every text.

**Architecture:** A new `orion/trading/autopilot.py` holds every autonomous decision (`step()` opens on fresh signals, `guard()` runs the account stop, the stop guard, the 48-hour time stop and the journal reconcile). `exchange.py` gets dialog-free `auto_place` / `auto_close` that only work while REAL TRADE is on, plus `ensure_stop`, `transfers_since` and `smallest_check`. The watch calls the autopilot; `modes.set_real` asks before a voice switch-on; `self_improve` keeps Orion-written code out of `orion.trading`.

**Tech Stack:** Python 3.12, hyperliquid-python-sdk (already installed), pytest; React 19 + Vite 8 + Vitest for the window; headless Edge e2e (`web/e2e/run.py`, start it from the **PowerShell** tool).

**Spec:** `docs/superpowers/specs/2026-10-03-autonomous-trading-design.md`

## Global Constraints

- Risk per trade 2 % of the account at the stop; ≤10x; ≤6 % lost per day; ≤3 open positions — unchanged (`risk.Limits`).
- Account stop: `max_drawdown_pct = 40.0` — REAL TRADE switches itself off when the account is 40 % below its high (deposits and withdrawals excluded).
- Only strategies with `backtest.is_enabled(report, coin, strategy)` are traded by the autopilot; the language model never decides a trade.
- Every autopilot order goes through `risk.plan`; stop and target sit on the exchange (`grouping="normalTpsl"`).
- Trades sir asks for by voice/chat keep the „Одобри“ dialog (`exchange.place`, `exchange.close`, `exchange.move_stop_to_entry` unchanged).
- The window button switches REAL TRADE at once; voice/chat switch-on asks (`confirm.ask`, button „Включи“); switching off never asks.
- Voice only 08:00–23:00 (`voice_hours`), the journal always; an error is told at most every 6 hours.
- Code Orion writes itself may not import `orion.trading` (any module) — checked in `self_improve.validate_skill_code`.
- Trust Wallet appears nowhere in Orion's texts, the key dialog or the README (old specs/plans stay as history).
- Spoken/visible Orion texts are Bulgarian; window labels/tooltips are English (as the window is today).
- Lines ≤120 characters; no new dependencies; never commit `trading_settings.json`, `memory/`, `logs/`.
- Tests: `python -m pytest -q` from the project root; `npx vitest run` and `npm run build` in `web/`; e2e from PowerShell: `python web\e2e\run.py`.
- Work on a branch `autonomous-trading` from `main`; do not push unless sir asks.

## Review Focus

1. **Switching testnet ↔ mainnet while REAL TRADE is on** — the account stop must not compare the mainnet balance with the testnet high; each network gets its own high. Test: `test_another_network_has_its_own_high` (Task 3).
2. **A deposit reaching the ledger before the first check after switching on** must not be counted twice into the high. Test: `test_a_deposit_before_the_first_check_is_not_counted_twice` (Task 3).
3. **Orion restarted on the same candle** — a signal already decided must never be traded again (the decided list lives in `memory/trading_auto.json`). Test: `test_decided_signals_are_remembered_after_a_restart` (Task 3).
4. **Sir's money still in Phantom's spot balance (perps account value 0)** — Orion must say so (once per 6 hours) instead of silently doing nothing. Test: `test_an_empty_perps_account_is_said_once_per_6_hours` (Task 3); the live probe in Task 8 checks the real account before the first trade.
5. **Sir closes an autopilot position by hand in Phantom** — no time stop or stop guard on a position that is gone; the journal trade is closed. Test: `test_a_trade_without_a_position_is_reconciled_silently` (Task 3).

## File map

| File | Change |
|---|---|
| `orion/trading/risk.py` | `Limits.max_drawdown_pct = 40.0` |
| `orion/trading/settings.py` | default limit `max_drawdown_pct`; comment of `enabled` |
| `orion/trading/journal.py` | `add_trade(..., auto=False)`, `open_trades()` |
| `orion/trading/exchange.py` | `_open`/`_close` split; `auto_place`, `auto_close`, `ensure_stop`, `perp_flow`, `transfers_since`, `smallest_check`; docstring |
| `orion/trading/autopilot.py` | **new** — `step`, `guard`, `reset_peak`, `stale`, account stop |
| `orion/trading/texts.py` | autopilot lines; Phantom connect steps; new mainnet warning; `autopilot_terms` |
| `orion/trading/modes.py` | `set_real(on, by_button=False)` with the voice dialog and `reset_peak` |
| `orion/trading/watcher.py` | autopilot in `scan`, guard in `positions`, reminder only for sir's trades, `tell` |
| `orion/trading/__init__.py` | docstring |
| `orion/self_improve.py` | `TRADING_BAN`, `_reaches_trading` |
| `skills/crypto_trading_skills.py` | docstrings, `NEITHER`, network-switch text |
| `app.py` | `HudApi.set_real_trading` passes `by_button=True` |
| `config.py` | persona sentence about trades |
| `web/src/components/Console.jsx`, `KeyDialog.jsx` (+ tests) | tooltip, wallet label; `ui/` rebuilt |
| `README.md` | trading section: Phantom, autopilot |
| tests | `conftest.py` (autouse state file), new `test_trading_autopilot.py`, `test_self_improve_trading.py`; updates in exchange/journal/settings/modes/skills/demo-skills/app/watcher tests |

Every code block below was run in a scratch clone of `main` at 528933d: pytest 275 passed, vitest 50 passed, `npm run build` ok, e2e 37 passed.

---

### Task 0: Branch

- [ ] **Step 1: Create the branch**

```bash
git checkout -b autonomous-trading
python -m pytest -q
```
Expected: `223 passed`.

---

### Task 1: The account-stop limit and autopilot trades in the journal

**Files:**
- Modify: `orion/trading/risk.py` (module docstring, `Limits`)
- Modify: `orion/trading/settings.py` (`DEFAULTS`)
- Modify: `orion/trading/journal.py` (`add_trade`, new `open_trades`)
- Test: `tests/test_trading_settings.py`, `tests/test_trading_journal.py`

**Interfaces:**
- Produces: `risk.Limits.max_drawdown_pct: float = 40.0`; `journal.add_trade(plan, strategy: str, auto: bool = False) -> None` (entry gets `"auto": bool`); `journal.open_trades() -> list[dict]` (open real trades, oldest first; each has `coin, side, stop, target, time, auto`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_trading_settings.py`, inside `test_defaults_are_the_testnet_and_the_aggressive_limits`, after the line
`assert (limits.risk_pct, limits.max_leverage, limits.daily_loss_pct, limits.max_positions) == (2.0, 10, 6.0, 3)` add:

```python
    assert limits.max_drawdown_pct == 40.0
```

Append to `tests/test_trading_settings.py`:

```python


def test_a_settings_file_from_before_gets_the_account_stop():
    settings.SETTINGS_FILE.write_text('{"limits": {"risk_pct": 1.0}}', encoding="utf-8")
    limits = settings.limits()
    assert (limits.risk_pct, limits.max_drawdown_pct) == (1.0, 40.0)
```

Append to `tests/test_trading_journal.py`:

```python


def test_autopilot_trades_are_marked_and_listed_while_open():
    from orion.trading import risk
    plan = risk.OrderPlan("BTC", "long", 0.01, 100.0, 99.0, 102.0, 2, 1.0, 0.5, 0.01, 0.02, 50.0, 0.001, "mainnet")
    journal.add_trade(plan, "breakout", auto=True)
    journal.add_trade(risk.OrderPlan("ETH", "short", 0.1, 2000.0, 2050.0, 1900.0, 2, 200.0, 100.0, 5.0, 10.0,
                                     2500.0, 0.2, "mainnet"), "без сигнал")
    found = journal.open_trades()
    assert [(e["coin"], e["auto"], e["stop"]) for e in found] == [("BTC", True, 99.0), ("ETH", False, 2050.0)]
    journal.close_trade("BTC", 102.0, 2.0)
    assert [e["coin"] for e in journal.open_trades()] == ["ETH"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q tests/test_trading_settings.py tests/test_trading_journal.py`
Expected: FAIL — `AttributeError: 'Limits' object has no attribute 'max_drawdown_pct'`, `TypeError: add_trade() got an unexpected keyword argument 'auto'`.

- [ ] **Step 3: Implement**

`orion/trading/risk.py` — replace the module docstring's last line
`≤6 % lost per day, ≤3 open positions. Isolated margin; the liquidation must be ≥1.5× further than the stop.`
with:

```python
≤6 % lost per day, ≤3 open positions. Isolated margin; the liquidation must be ≥1.5× further than the stop.
max_drawdown_pct is the autopilot's account stop: REAL TRADE switches itself off 40 % below the account's high.
```

and in `class Limits` after `max_positions: int = 3` add:

```python
    max_drawdown_pct: float = 40.0
```

`orion/trading/settings.py` — in `DEFAULTS` replace

```python
    "enabled": False,      # REAL TRADE button — real orders only while it is on
```
with
```python
    "enabled": False,      # REAL TRADE button — Orion trades the real account by itself while it is on
```
and replace
```python
    "limits": {"risk_pct": 2.0, "max_leverage": 10, "daily_loss_pct": 6.0, "max_positions": 3},
```
with
```python
    "limits": {"risk_pct": 2.0, "max_leverage": 10, "daily_loss_pct": 6.0, "max_positions": 3,
               "max_drawdown_pct": 40.0},
```

`orion/trading/journal.py` — replace the whole `add_trade` function with:

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q tests/test_trading_settings.py tests/test_trading_journal.py tests/test_trading_risk.py`
Expected: all pass. Then `python -m pytest -q` → `225 passed`.

- [ ] **Step 5: Commit**

```bash
git add orion/trading/risk.py orion/trading/settings.py orion/trading/journal.py tests/test_trading_settings.py tests/test_trading_journal.py
git commit -m "Trading: account-stop limit (40 %) and autopilot trades marked in the journal"
```

---

### Task 2: Dialog-free orders for the autopilot, the stop guard, the ledger and the smallest check

**Files:**
- Modify: `orion/trading/exchange.py`
- Test: `tests/test_trading_exchange.py`

**Interfaces:**
- Consumes: `settings.enabled() -> bool` (exists).
- Produces (used by Task 3):
  - `exchange.auto_place(plan: risk.OrderPlan) -> str` — "Отворих …" or "Входът не се изпълни …"; raises `TradingError("REAL TRADE е спрян — автопилотът не търгува.")` while REAL TRADE is off, `TradingError("В тест режим …")` when blocked, `TradingError("Цената се помести …")` if the price moved > 0.3 %, `TradingError(SENT_UNCHECKED)` when the result could not be read.
  - `exchange.auto_close(coins: list[str], network: str) -> str` — "Затворих: Биткойн." / "Няма какво да затварям."; same REAL TRADE guard.
  - `exchange.ensure_stop(coin: str, network: str, stop: float) -> str | None`
  - `exchange.perp_flow(delta: dict, address: str) -> float`; `exchange.transfers_since(network: str, since_ms: int) -> tuple[float, int]`
  - `exchange.smallest_check(network: str) -> str` (`testnet_check()` now calls `smallest_check("testnet")`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_trading_exchange.py`:

Replace `from orion.trading import exchange, risk` with:

```python
from orion.trading import exchange, risk, settings
```

In `FakeInfo.__init__`, after `self.fills: list[dict] = []` add:

```python
        self.ledger: list[dict] = []
```

In `FakeInfo`, after `user_funding_history` add:

```python
    def user_non_funding_ledger_updates(self, address, since):
        return [entry for entry in self.ledger if entry["time"] >= since]
```

Append to the end of the file:

```python


# --- The autopilot's orders: no dialog, only while REAL TRADE is on --------------------------------
@pytest.fixture
def real_trade(monkeypatch):
    monkeypatch.setattr(settings, "enabled", lambda: True)


def test_auto_place_opens_with_stop_and_target_without_a_dialog(fake, approve, real_trade):
    info, ex = fake
    asked = approve(False)
    answer = exchange.auto_place(plan())
    assert answer.startswith("Отворих лонг на Биткойн") and asked == []
    kind, orders, grouping = ex.calls[1]
    assert (kind, grouping) == ("bulk", "normalTpsl") and orders[2]["order_type"]["trigger"]["tpsl"] == "sl"
    assert exchange.last_open == {"BTC"}


def test_the_autopilot_cannot_trade_while_real_trade_is_off(fake, monkeypatch):
    info, ex = fake
    monkeypatch.setattr(settings, "enabled", lambda: False)
    with pytest.raises(exchange.TradingError, match="REAL TRADE е спрян"):
        exchange.auto_place(plan())
    with pytest.raises(exchange.TradingError, match="REAL TRADE е спрян"):
        exchange.auto_close(["BTC"], "testnet")
    assert ex.used == [] and ex.calls == []


def test_the_autopilot_cannot_trade_in_test_mode(fake, real_trade, monkeypatch):
    info, ex = fake
    monkeypatch.setattr(exchange, "blocked", True)
    with pytest.raises(exchange.TradingError, match="тест режим"):
        exchange.auto_place(plan())
    assert ex.calls == []


def test_auto_place_skips_when_the_price_moved(fake, real_trade):
    info, ex = fake
    info.mid = 100.5
    with pytest.raises(exchange.TradingError, match="помести"):
        exchange.auto_place(plan())
    assert ex.calls == []


def test_auto_close_closes_and_cancels_without_a_dialog(fake, approve, real_trade):
    info, ex = fake
    info.positions = [{"coin": "BTC", "szi": "0.5", "entryPx": "100", "unrealizedPnl": "3.2"}]
    info.orders = [{"coin": "BTC", "isTrigger": True, "reduceOnly": True, "triggerPx": "99", "oid": 7}]
    asked = approve(False)
    assert exchange.auto_close(["BTC", "ETH"], "testnet") == "Затворих: Биткойн."
    assert ("close", "BTC") in ex.calls and ("cancel", "BTC", 7) in ex.calls and asked == []
    assert exchange.auto_close(["BTC"], "testnet") == "Няма какво да затварям."


def test_ensure_stop_leaves_a_stop_that_is_there(fake):
    info, ex = fake
    info.positions = [{"coin": "BTC", "szi": "0.5", "entryPx": "100", "unrealizedPnl": "0"}]
    info.orders = [{"coin": "BTC", "isTrigger": True, "reduceOnly": True, "triggerPx": "98", "oid": 3}]
    assert exchange.ensure_stop("BTC", "testnet", 98.0) is None and ex.calls == []
    assert exchange.ensure_stop("ETH", "testnet", 1900.0) is None


def test_ensure_stop_puts_back_a_missing_stop(fake):
    info, ex = fake
    info.positions = [{"coin": "BTC", "szi": "-0.5", "entryPx": "100", "unrealizedPnl": "0"}]
    assert exchange.ensure_stop("BTC", "testnet", 102.0) == "Позицията в биткойн беше без стоп — поставих го на 102.00."
    kind, order = ex.calls[0]
    assert kind == "order" and order["is_buy"] and order["order_type"]["trigger"]["tpsl"] == "sl"


def test_ensure_stop_closes_when_the_stop_cannot_be_placed(fake):
    info, ex = fake
    ex.place_stop = False
    info.positions = [{"coin": "BTC", "szi": "0.5", "entryPx": "100", "unrealizedPnl": "0"}]
    assert "затворих я веднага" in exchange.ensure_stop("BTC", "testnet", 98.0)
    assert ("close", "BTC") in ex.calls and info.positions == []


def test_transfers_count_only_money_moved_into_or_out_of_perps(fake):
    info, ex = fake
    info.ledger = [
        {"time": 10, "delta": {"type": "deposit", "usdc": "100"}},
        {"time": 11, "delta": {"type": "withdraw", "usdc": "30", "fee": "1"}},
        {"time": 12, "delta": {"type": "accountClassTransfer", "usdc": "50", "toPerp": True}},
        {"time": 13, "delta": {"type": "accountClassTransfer", "usdc": "20", "toPerp": False}},
        {"time": 14, "delta": {"type": "internalTransfer", "usdc": "10", "user": "0xother", "destination": "0xME"}},
        {"time": 15, "delta": {"type": "subAccountTransfer", "usdc": "5", "user": "0xme", "destination": "0xsub"}},
        {"time": 16, "delta": {"type": "send", "token": "USDC", "usdcValue": "7", "user": "0xme",
                               "destination": "0xme", "sourceDex": "spot", "destinationDex": ""}},
        {"time": 17, "delta": {"type": "spotTransfer", "token": "USDC", "amount": "9", "user": "0xme"}},
        {"time": 18, "delta": {"type": "liquidation", "accountValue": "0"}},
    ]
    assert exchange.transfers_since("testnet", 0) == (pytest.approx(112.0), 18)
    assert exchange.transfers_since("testnet", 15) == (pytest.approx(2.0), 18)
    assert exchange.transfers_since("testnet", 19) == (0.0, 0)


def test_the_smallest_check_on_the_real_account(fake):
    info, ex = fake
    answer = exchange.smallest_check("mainnet")
    assert ex.used == ["mainnet"] and answer.startswith("Проверката в истинската сметка мина")
    assert info.positions == [] and info.orders == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q tests/test_trading_exchange.py`
Expected: 10 failed (`AttributeError: module 'orion.trading.exchange' has no attribute 'auto_place'` etc.), 13 passed.

- [ ] **Step 3: Implement in `orion/trading/exchange.py`**

Replace the module docstring's first paragraph

```python
"""
The only place that talks to Hyperliquid with a key. Every open and every close passes through
confirm.ask (sir's „Одобри“) HERE — not in the skills — so no skill, including code Orion writes itself,
can trade without sir. The agent (API) key can trade but cannot withdraw.
```
with
```python
"""
The only place that talks to Hyperliquid with a key (Phantom's Perps tab is this Hyperliquid account).
Every open and close a skill asks for (voice, chat) passes through confirm.ask (sir's „Одобри“) HERE.
Only the autopilot calls auto_place / auto_close: they work only while REAL TRADE is on, and every order
they send was made by risk.plan within the hard limits. Code Orion writes itself may not import this
module (self_improve). The agent (API) key can trade but cannot withdraw.
```
(the second paragraph, "After approval the price is read again…", stays).

Replace the head of `place()` — from `def place(plan: risk.OrderPlan, note: str = "") -> str:` down to and including `    position = _send(info, client, address, plan, mid)` — with:

```python
def _open(info, client, address: str, plan: risk.OrderPlan, mid: float) -> str:
    """Sends the entry with its target and stop and makes sure the stop exists. Returns what Orion says."""
    position = _send(info, client, address, plan, mid)
```

Right after the end of that function (after its final `return (f"Отворих …" … "— и двата са в борсата.")`), add:

```python


def place(plan: risk.OrderPlan, note: str = "") -> str:
    """Asks sir; on „Одобри“ opens the position with its stop and target. Returns what Orion says."""
    info, client, address = _client(plan.network)
    title, summary, body = confirmation(plan, note)
    if not confirm.ask(title, summary, body, "Одобри сделката"):
        return "Добре, сър — сделката не е отворена."
    mid = float(info.all_mids()[plan.coin])
    if abs(mid / plan.entry - 1) > MOVE_LIMIT:
        raise PriceMoved(mid)
    return _open(info, client, address, plan, mid)


def _autopilot_client(network: str):
    if not settings.enabled():
        raise TradingError("REAL TRADE е спрян — автопилотът не търгува.")
    return _client(network)


def auto_place(plan: risk.OrderPlan) -> str:
    """The autopilot's open — no dialog: only while REAL TRADE is on. Returns what Orion says."""
    info, client, address = _autopilot_client(plan.network)
    mid = float(info.all_mids()[plan.coin])
    if abs(mid / plan.entry - 1) > MOVE_LIMIT:
        raise TradingError("Цената се помести, докато смятах сделката — пропускам я.")
    return _open(info, client, address, plan, mid)
```

The result for `_open` must read exactly:

```python
def _open(info, client, address: str, plan: risk.OrderPlan, mid: float) -> str:
    """Sends the entry with its target and stop and makes sure the stop exists. Returns what Orion says."""
    position = _send(info, client, address, plan, mid)
    if not position:
        return "Входът не се изпълни — цената избяга. Нищо не е отворено."
    try:
        _protect(info, client, address, plan, position)
    except TradingError:
        raise
    except Exception as e:  # the position is open; the stop check itself failed
        last_open.add(plan.coin)
        raise TradingError(SENT_UNCHECKED) from e
    last_open.add(plan.coin)
    return (f"Отворих {'лонг' if plan.side == 'long' else 'шорт'} на {NAMES[plan.coin]}: {position['size']:g} на "
            f"{_fmt(position['entry'])}. Стоп {_fmt(plan.stop)}, цел {_fmt(plan.target)} — и двата са в борсата.")
```

In `close()`, replace the loop at its end

```python
    done = []
    for coin in wanted:
        _ok(client.market_close(coin, slippage=CLOSE_SLIPPAGE), f"Затварянето на {NAMES[coin]}")
        for order in info.frontend_open_orders(address):
            if order.get("coin") == coin and order.get("reduceOnly"):
                client.cancel(coin, order["oid"])
        last_open.discard(coin)
        done.append(f"{NAMES[coin]} ({pnl[coin]:+.2f} $)")
    return "Затворих: " + ", ".join(done) + "."
```
with
```python
    done = []
    for coin in wanted:
        _close(info, client, address, coin)
        done.append(f"{NAMES[coin]} ({pnl[coin]:+.2f} $)")
    return "Затворих: " + ", ".join(done) + "."


def _close(info, client, address: str, coin: str) -> None:
    """Closes one position at market and cancels its stop and target."""
    _ok(client.market_close(coin, slippage=CLOSE_SLIPPAGE), f"Затварянето на {NAMES[coin]}")
    for order in info.frontend_open_orders(address):
        if order.get("coin") == coin and order.get("reduceOnly"):
            client.cancel(coin, order["oid"])
    last_open.discard(coin)


def auto_close(coins: list[str], network: str) -> str:
    """The autopilot's close (the 48-hour time stop) — no dialog: only while REAL TRADE is on."""
    info, client, address = _autopilot_client(network)
    open_now = {item["position"]["coin"] for item in info.user_state(address).get("assetPositions", [])
                if float(item["position"]["szi"])}
    closed = [coin for coin in coins if coin in open_now]
    for coin in closed:
        _close(info, client, address, coin)
    return ("Затворих: " + ", ".join(NAMES[c] for c in closed) + ".") if closed else "Няма какво да затварям."


def ensure_stop(coin: str, network: str, stop: float) -> str | None:
    """The autopilot's stop guard: a position without a stop on the exchange gets one at `stop`; if even that
    fails, it is closed at once. Returns what Orion says, or None when the stop is there."""
    info, client, address = _client(network)
    position = _position(info, address, coin)
    if not position:
        return None
    stops, _ = _protection(info, address, coin, position["side"], position["entry"])
    if stops:
        return None
    decimals = next(int(u["szDecimals"]) for u in info.meta()["universe"] if u["name"] == coin)
    _place_trigger(client, coin, position["side"] == "short", position["size"], stop, "sl", decimals)
    time.sleep(SETTLE)
    stops, _ = _protection(info, address, coin, position["side"], position["entry"])
    name = NAMES[coin].lower()
    if stops:
        return f"Позицията в {name} беше без стоп — поставих го на {_fmt(stop)}."
    _close(info, client, address, coin)
    return f"Позицията в {name} беше без стоп и не успях да го поставя — затворих я веднага."
```

After `fills_since` add:

```python


def perp_flow(delta: dict, address: str) -> float:
    """USDC one ledger entry moved into (+) or out of (−) the perps account; 0 for anything else.
    Fees are left out: the account stop then errs on the early side, never the late one."""
    kind = delta.get("type")
    usdc = float(delta.get("usdc") or 0)
    me = address.lower()
    to_me = str(delta.get("destination", "")).lower() == me
    from_me = str(delta.get("user", "")).lower() == me
    if kind == "deposit":
        return usdc
    if kind == "withdraw":
        return -usdc
    if kind == "accountClassTransfer":
        return usdc if delta.get("toPerp") else -usdc
    if kind in ("internalTransfer", "subAccountTransfer"):
        return usdc if to_me else -usdc if from_me else 0.0
    if kind == "vaultDeposit":
        return -usdc
    if kind == "vaultWithdraw":
        return float(delta.get("netWithdrawnUsd") or 0)
    if kind == "send" and delta.get("token") == "USDC":
        value = float(delta.get("usdcValue") or delta.get("amount") or 0)
        into = to_me and delta.get("destinationDex", "") == ""
        out = from_me and delta.get("sourceDex", "") == ""
        return value * (into - out)
    return 0.0


def transfers_since(network: str, since_ms: int) -> tuple[float, int]:
    """(USDC moved into (+) / out of (−) the perps account since since_ms, time of the newest ledger entry or 0) —
    so the account stop never takes a deposit or a withdrawal for profit or loss."""
    info, _, address = _client(network)
    total, last = 0.0, 0
    for entry in info.user_non_funding_ledger_updates(address, since_ms):
        total += perp_flow(entry.get("delta") or {}, address)
        last = max(last, int(entry.get("time") or 0))
    return total, last
```

Replace the head of `testnet_check()`

```python
def testnet_check() -> str:
    """Test mode's daily check: the smallest BTC long on the TESTNET, its stop and target verified, then
    closed. Always the testnet (the network is fixed here), even while the sandbox blocks everything else."""
    info, client, address = client_factory("testnet")
    if _position(info, address, "BTC"):
        return "Проверката в тестовата мрежа е пропусната — там вече има позиция в биткойн."
```
with
```python
def testnet_check() -> str:
    """Test mode's daily check — always the testnet, even while the sandbox blocks everything else."""
    return smallest_check("testnet")


def smallest_check(network: str) -> str:
    """The smallest BTC long (≈11 $), its stop and target verified, then closed at once. The testnet daily
    (testnet_check); the real account once, on sir's word, before the autopilot's first real trade."""
    info, client, address = client_factory(network)
    where = "в тестовата мрежа" if network == "testnet" else "в истинската сметка"
    if _position(info, address, "BTC"):
        return f"Проверката {where} е пропусната — там вече има позиция в биткойн."
```

and in the rest of that function replace:
- `"testnet", sz_decimals=decimals)` → `network, sz_decimals=decimals)`
- `return "Проверката в тестовата мрежа: входът не се изпълни."` → `return f"Проверката {where}: входът не се изпълни."`
- `return "Проверката в тестовата мрежа мина: входът, стопът и целта се поставиха и позицията се затвори."` → `return f"Проверката {where} мина: входът, стопът и целта се поставиха и позицията се затвори."`
- `return "Проверката в тестовата мрежа НЕ мина: стопът или целта липсваха. Позицията е затворена."` → `return f"Проверката {where} НЕ мина: стопът или целта липсваха. Позицията е затворена."`

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q tests/test_trading_exchange.py` → `23 passed`; `python -m pytest -q` → `235 passed`.

- [ ] **Step 5: Commit**

```bash
git add orion/trading/exchange.py tests/test_trading_exchange.py
git commit -m "Exchange: auto_place/auto_close only while REAL TRADE is on, stop guard, ledger flows, smallest check"
```

---

### Task 3: The autopilot

**Files:**
- Create: `orion/trading/autopilot.py`
- Modify: `orion/trading/texts.py` (autopilot lines)
- Modify: `tests/conftest.py` (autouse state file)
- Test: `tests/test_trading_autopilot.py` (new)

**Interfaces:**
- Consumes: Task 1 (`journal.add_trade(..., auto=True)`, `journal.open_trades()`, `Limits.max_drawdown_pct`), Task 2 (`exchange.auto_place`, `auto_close`, `ensure_stop`, `transfers_since`, `SENT_UNCHECKED`), existing `exchange.account_state(network) -> (risk.AccountState, {coin: {"mid", "sz_decimals", "max_leverage"}})`, `signals.latest(prepared)`, `backtest.is_enabled(report, coin, strategy)`, `trading.on_switch(name, on)`.
- Produces (used by Tasks 4 and 5):
  - `autopilot.step(prepared_by_coin: dict, report: dict | None, network: str) -> list[tuple[str, bool]]` — (line, say it out loud).
  - `autopilot.guard(network: str, account: risk.AccountState) -> list[tuple[str, bool]]`.
  - `autopilot.reset_peak() -> None`; `autopilot.load() -> dict`; `autopilot.save(state: dict) -> None`; `autopilot.AUTO_FILE`.
  - `texts.AUTO_NO_CONNECTION`, `texts.AUTO_EMPTY`, `texts.auto_opened(plan, strategy)`, `texts.auto_skipped(signal, reason)`, `texts.auto_unchecked(coin)`, `texts.auto_time_stop(coin, side)`, `texts.account_stop(peak, equity)`.

- [ ] **Step 1: The state file per test**

Append to `tests/conftest.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def autopilot_state(monkeypatch, tmp_path):
    """Every test gets its own memory/trading_auto.json — switching REAL TRADE on writes it."""
    from orion.trading import autopilot
    monkeypatch.setattr(autopilot, "AUTO_FILE", tmp_path / "trading_auto.json")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_trading_autopilot.py`:

```python
import pytest

from orion import trading
from orion.trading import autopilot, data, exchange, journal, risk, settings, signals, texts
from orion.trading.signals import Signal

GOOD = {"trades": 40, "win_rate": 0.5, "win_low": 0.35, "win_high": 0.65, "avg_r": 0.3, "profit_factor": 1.6,
        "max_drawdown_r": 5.0}
REPORT = {"time": 0, "coins": {"BTC": {"breakout": GOOD}, "ETH": {"breakout": GOOD}}}
PREPARED = {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL"}   # signals.latest is replaced: it gets the coin
T0 = 1_790_000_000_000


class Exchange:
    """A stand-in for exchange.py: the account, the orders the autopilot sends, the closes."""

    def __init__(self):
        self.equity, self.lost, self.positions = 1000.0, 0.0, {}
        self.mids = {"BTC": 100.0, "ETH": 2000.0, "SOL": 150.0}
        self.placed, self.closed, self.checked = [], [], []
        self.flows = (0.0, 0)
        self.down = False      # account_state raises OSError
        self.fail = None       # auto_place raises this
        self.stop_said = None  # what ensure_stop returns

    def account_state(self, network):
        if self.down:
            raise OSError("connection reset")
        coins = {coin: {"mid": mid, "sz_decimals": 3, "max_leverage": 20} for coin, mid in self.mids.items()}
        return risk.AccountState(self.equity, dict(self.positions), self.lost), coins

    def auto_place(self, plan):
        if self.fail:
            raise self.fail
        self.placed.append(plan)
        self.positions[plan.coin] = {"side": plan.side, "size": plan.size, "entry": plan.entry, "pnl": 0.0,
                                     "liq": 0.0, "value": plan.notional}
        return f"Отворих лонг на {plan.coin}."

    def auto_close(self, coins, network):
        self.closed += coins
        for coin in coins:
            self.positions.pop(coin, None)
        return "Затворих."

    def ensure_stop(self, coin, network, stop):
        self.checked.append((coin, stop))
        return self.stop_said

    def transfers_since(self, network, since):
        return self.flows


@pytest.fixture
def ex(monkeypatch, tmp_path):
    fake = Exchange()
    for name in ("account_state", "auto_place", "auto_close", "ensure_stop", "transfers_since"):
        monkeypatch.setattr(exchange, name, getattr(fake, name))
    monkeypatch.setattr(journal, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    settings.set_enabled(True)
    fake.found = {"BTC": [], "ETH": [], "SOL": []}
    monkeypatch.setattr(signals, "latest", lambda p: fake.found[p])
    fake.switched = []
    monkeypatch.setattr(trading, "on_switch", lambda name, on: fake.switched.append((name, on)))
    clock = {"now": T0}
    monkeypatch.setattr(autopilot, "_now", lambda: clock["now"])
    monkeypatch.setattr(journal, "_now", lambda: clock["now"])
    fake.clock = clock
    return fake


def sig(coin="BTC", side="long", time=1, strategy="breakout", entry=100.0, stop=98.0, target=104.0):
    return Signal(coin, strategy, side, time, entry, stop, target, 4, [])


def step(ex):
    return autopilot.step(PREPARED, REPORT, "mainnet")


def guard(ex):
    return autopilot.guard("mainnet", ex.account_state("mainnet")[0])


# --- Opening ------------------------------------------------------------------------------------
def test_a_fresh_checked_signal_is_traded_with_its_own_levels_and_2_percent_risk(ex):
    ex.found["BTC"] = [sig()]
    lines = step(ex)
    plan = ex.placed[0]
    assert (plan.coin, plan.side, plan.entry, plan.stop, plan.target) == ("BTC", "long", 100.0, 98.0, 104.0)
    assert plan.risk_usd == pytest.approx(20.0) and plan.network == "mainnet"
    assert lines == [(texts.auto_opened(plan, "breakout"), True)]
    assert lines[0][0].startswith("Отворих лонг на биткойн — пробив: 10 BTC")
    assert [(t["coin"], t["auto"]) for t in journal.open_trades()] == [("BTC", True)]


def test_unchecked_strategies_are_not_traded(ex):
    ex.found["BTC"] = [sig(strategy="pullback")]
    ex.found["SOL"] = [sig(coin="SOL", entry=150.0, stop=147.0, target=156.0)]
    assert step(ex) == [] and ex.placed == []


def test_a_signal_is_decided_once(ex):
    ex.found["BTC"] = [sig()]
    step(ex)
    assert step(ex) == [] and len(ex.placed) == 1
    ex.found["BTC"] = [sig(time=2)]                     # a new candle, but the coin already has a position
    lines = step(ex)
    assert len(ex.placed) == 1 and len(lines) == 1
    text, loud = lines[0]
    assert not loud and text.startswith("Пропуснах сигнал за лонг на биткойн (пробив): Вече имате позиция")


def test_two_coins_in_one_scan(ex):
    ex.found["BTC"] = [sig()]
    ex.found["ETH"] = [sig(coin="ETH", side="short", entry=2000.0, stop=2040.0, target=1920.0)]
    lines = step(ex)
    assert [p.coin for p in ex.placed] == ["BTC", "ETH"] and all(loud for _, loud in lines)


def test_stale_means_a_third_of_the_way_to_the_target_or_the_stop():
    long, short = sig(), sig(side="short", stop=102.0, target=96.0)
    assert not autopilot.stale(long, 101.3) and autopilot.stale(long, 101.4)
    assert not autopilot.stale(long, 99.4) and autopilot.stale(long, 99.3)
    assert not autopilot.stale(short, 98.7) and autopilot.stale(short, 98.6)
    assert not autopilot.stale(short, 100.6) and autopilot.stale(short, 100.7)


def test_a_stale_signal_goes_into_the_journal_only(ex):
    ex.mids["BTC"] = 101.5
    ex.found["BTC"] = [sig()]
    assert step(ex) == [(texts.auto_skipped(sig(), "цената вече измина над една трета от пътя до целта или стопа."),
                         False)]
    assert ex.placed == []


def test_the_daily_loss_limit_and_the_position_limit_hold(ex):
    ex.lost = 60.0
    ex.found["BTC"] = [sig()]
    (text, loud), = step(ex)
    assert "Днешният лимит на загуба" in text and not loud and ex.placed == []
    ex.lost = 0.0
    ex.positions = {c: {"side": "long", "size": 1, "entry": 1, "pnl": 0, "liq": 0, "value": 1} for c in ("A", "B", "C")}
    ex.found["BTC"] = [sig(time=2)]
    (text, loud), = step(ex)
    assert "лимитът" in text and ex.placed == []


def test_a_connection_error_leaves_the_signal_for_the_next_scan(ex):
    ex.found["BTC"] = [sig()]
    ex.down = True
    assert step(ex) == [(texts.AUTO_NO_CONNECTION, True)]
    assert step(ex) == []                              # said once per 6 hours
    ex.down = False
    step(ex)
    assert len(ex.placed) == 1


def test_an_exchange_refusal_is_journalled_and_said_once_per_6_hours(ex):
    ex.fail = exchange.TradingError("Поръчката: API ключът не е одобрен или е изтекъл.")
    ex.found["BTC"] = [sig()]
    (text, loud), = step(ex)
    assert loud and "API ключът" in text
    ex.found["BTC"] = [sig(time=2)]
    (text, loud), = step(ex)
    assert not loud and "API ключът" in text
    ex.clock["now"] += 6 * 3_600_000
    ex.found["BTC"] = [sig(time=3)]
    assert step(ex)[0][1] is True


@pytest.mark.parametrize("failure", [exchange.TradingError(exchange.SENT_UNCHECKED), TimeoutError("read timeout")])
def test_an_order_without_an_answer_is_journalled_for_the_guard(ex, failure):
    ex.fail = failure
    ex.found["BTC"] = [sig()]
    assert step(ex) == [(texts.auto_unchecked("BTC"), True)]
    assert [(t["coin"], t["auto"]) for t in journal.open_trades()] == [("BTC", True)]
    assert step(ex) == []                              # decided — not sent twice


# --- Guarding -----------------------------------------------------------------------------------
def test_the_account_stop_fires_on_the_second_check_below_the_floor(ex):
    autopilot.reset_peak()
    assert guard(ex) == []
    ex.equity = 1200.0
    assert guard(ex) == []
    ex.equity = 719.0                                  # floor = 1200 × 0.6 = 720
    assert guard(ex) == [] and settings.enabled()
    (text, loud), = guard(ex)
    assert loud and text.startswith("Сър, сметката падна с 40 % от най-високата си стойност (от 1 200 $ на 719.00 $)")
    assert not settings.enabled() and ex.switched == [("real", False)]


def test_one_check_below_then_back_above_does_not_fire(ex):
    autopilot.reset_peak()
    guard(ex)
    ex.flows = (1000.0, T0 + 5)                        # a deposit reached the ledger before the balance
    assert guard(ex) == []
    ex.flows, ex.equity = (0.0, 0), 2000.0
    assert guard(ex) == [] and settings.enabled()
    assert autopilot.load()["peak"] == 2000.0


def test_a_withdrawal_is_not_a_loss(ex):
    autopilot.reset_peak()
    guard(ex)
    ex.flows, ex.equity = (-500.0, T0 + 5), 500.0
    assert guard(ex) == [] and guard(ex) == []
    assert settings.enabled() and autopilot.load()["peak"] == 500.0
    ex.flows, ex.equity = (0.0, 0), 299.0              # 40 % below the 500 left
    guard(ex)
    assert guard(ex) and not settings.enabled()


def test_the_ledger_is_read_from_where_it_stopped(ex, monkeypatch):
    seen = []
    monkeypatch.setattr(exchange, "transfers_since", lambda network, since: (seen.append(since), (0.0, T0 + 9))[1])
    autopilot.reset_peak()
    guard(ex)
    guard(ex)
    assert seen == [T0, T0 + 10]


def test_switching_on_resets_the_high(ex):
    autopilot.reset_peak()
    guard(ex)
    assert autopilot.load()["peak"] == 1000.0
    autopilot.reset_peak()
    assert autopilot.load()["peak"] is None


def plan_for(coin, side="long", stop=98.0):
    return risk.OrderPlan(coin, side, 1.0, 100.0, stop, 104.0, 2, 100.0, 50.0, 2.0, 4.0, 60.0, 0.1, "mainnet")


def test_the_stop_guard_checks_only_the_autopilots_trades(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    journal.add_trade(plan_for("ETH", stop=1900.0), "без сигнал")
    ex.positions = {"BTC": {}, "ETH": {}}
    ex.stop_said = "Позицията в биткойн беше без стоп — поставих го на 98.00."
    assert guard(ex) == [(ex.stop_said, True)]
    assert ex.checked == [("BTC", 98.0)]


def test_the_time_stop_closes_only_the_autopilots_trades_after_48_hours(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    journal.add_trade(plan_for("ETH", stop=1900.0), "без сигнал")
    ex.positions = {"BTC": {}, "ETH": {}}
    ex.clock["now"] += 47 * data.HOUR
    assert guard(ex) == [] and ex.closed == []
    ex.clock["now"] += 1 * data.HOUR
    assert guard(ex) == [(texts.auto_time_stop("BTC", "long"), True)]
    assert ex.closed == ["BTC"]


def test_a_time_stop_that_fails_is_retried_but_said_once(ex, monkeypatch):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    ex.positions = {"BTC": {}}
    tries = []
    monkeypatch.setattr(exchange, "auto_close", lambda coins, network: tries.append(coins) or "Няма какво да затварям.")
    ex.clock["now"] += 49 * data.HOUR
    assert len(guard(ex)) == 1 and guard(ex) == []
    assert tries == [["BTC"], ["BTC"]]


def test_no_time_stop_after_real_trade_went_off(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    ex.positions = {"BTC": {}}
    settings.set_enabled(False)
    ex.clock["now"] += 49 * data.HOUR
    assert guard(ex) == [] and ex.closed == [] and ex.checked == [("BTC", 98.0)]


def test_a_trade_without_a_position_is_reconciled_silently(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    assert guard(ex) == [] and journal.open_trades() == [] and ex.checked == []


def test_the_guard_says_a_lost_connection_once_per_6_hours(ex, monkeypatch):
    def down(network, since):
        raise OSError("connection reset")
    monkeypatch.setattr(exchange, "transfers_since", down)
    account = risk.AccountState(1000.0)
    assert autopilot.guard("mainnet", account) == [(texts.AUTO_NO_CONNECTION, True)]
    assert autopilot.guard("mainnet", account) == []


# --- Review focus ---------------------------------------------------------------------------------
def test_another_network_has_its_own_high(ex):
    autopilot.reset_peak()
    autopilot.guard("testnet", risk.AccountState(10000.0))
    assert autopilot.guard("mainnet", risk.AccountState(200.0)) == []
    assert autopilot.guard("mainnet", risk.AccountState(200.0)) == []
    assert settings.enabled() and autopilot.load()["peak"] == 200.0


def test_a_deposit_before_the_first_check_is_not_counted_twice(ex):
    autopilot.reset_peak()
    ex.flows, ex.equity = (500.0, T0 + 1), 1500.0
    guard(ex)
    assert autopilot.load()["peak"] == 1500.0
    ex.flows, ex.equity = (0.0, 0), 950.0               # floor 900
    assert guard(ex) == [] and guard(ex) == [] and settings.enabled()


def test_decided_signals_are_remembered_after_a_restart(ex):
    ex.found["BTC"] = [sig()]
    step(ex)
    assert autopilot.load()["traded"] == [["BTC", "breakout", "long", 1]]
    ex.positions.clear()                                # sir closed it; Orion restarts on the same candle
    assert step(ex) == [] and len(ex.placed) == 1


def test_an_empty_perps_account_is_said_once_per_6_hours(ex):
    ex.equity = 0.0
    ex.found["BTC"] = [sig()]
    assert step(ex) == [(texts.AUTO_EMPTY, True)]
    ex.found["BTC"] = [sig(time=2)]
    assert step(ex) == [(texts.AUTO_EMPTY, False)] and ex.placed == []
```

- [ ] **Step 3: Run them to see them fail**

Run: `python -m pytest -q tests/test_trading_autopilot.py`
Expected: FAIL at collection/fixture — `ImportError: cannot import name 'autopilot' from 'orion.trading'` (and every other test errors in the conftest fixture until the module exists).

- [ ] **Step 4: The autopilot's texts**

In `orion/trading/texts.py`, right above the line `# --- Demo accounts and the simulation ---…`, insert:

```python
# --- The autopilot (REAL TRADE) ------------------------------------------------------------------
AUTO_NO_CONNECTION = "Нямам връзка с Hyperliquid — автопилотът ще опита пак след малко."
AUTO_EMPTY = ("Имаше сигнал, но в Perps сметката няма пари — внесете в Perps баланса в Phantom (от SOL или USDC) "
              "и ще търгувам.")


def auto_opened(plan, strategy: str) -> str:
    side = "лонг" if plan.side == "long" else "шорт"
    return (f"Отворих {side} на {NAMES[plan.coin].lower()} — {LABELS.get(strategy, strategy)}: {plan.size:g} "
            f"{plan.coin} (≈ {_fmt(plan.notional)} $), {plan.leverage}x, стоп {_fmt(plan.stop)}, цел "
            f"{_fmt(plan.target)}. Рискът е {plan.risk_usd:.2f} $.")


def auto_skipped(signal, reason: str) -> str:
    side = "лонг" if signal.side == "long" else "шорт"
    return (f"Пропуснах сигнал за {side} на {NAMES[signal.coin].lower()} "
            f"({LABELS.get(signal.strategy, signal.strategy)}): {reason}")


def auto_unchecked(coin: str) -> str:
    return (f"Връзката с борсата прекъсна, докато отварях сделка в {NAMES[coin].lower()}. При следващата проверка "
            f"ще видя дали позицията е отворена и дали има стоп.")


def auto_time_stop(coin: str, side: str) -> str:
    return f"Затварям {'лонг' if side == 'long' else 'шорт'} на {NAMES[coin].lower()} — изтекоха 48 часа."


def account_stop(peak: float, equity: float) -> str:
    fall = (1 - equity / peak) * 100 if peak else 0.0
    return (f"Сър, сметката падна с {fall:.0f} % от най-високата си стойност (от {_fmt(peak)} $ на {_fmt(equity)} $). "
            f"Спрях REAL TRADE — отворените позиции остават със стоповете си. Пуснете бутона пак, когато решите.")


```

- [ ] **Step 5: Create `orion/trading/autopilot.py`**

```python
"""
REAL TRADE's autopilot (docs/superpowers/specs/2026-10-03-autonomous-trading-design.md): while REAL TRADE is
on, Orion opens and closes real trades by itself — only on the strategies that passed the honest check,
every order through risk.plan's hard limits, the stop and the target on the exchange. The watch calls step()
every 15 minutes and guard() at every position check. Nothing here is a skill, so the language model cannot
reach it, and code Orion writes itself may not import the trading modules (self_improve).

memory/trading_auto.json: the account's high for the account stop and its network, where the
deposit/withdrawal count stopped, whether the last check was already below the floor, the signals already
decided, and when each error was last told.
"""
import json
import time

from .. import trading
from . import COINS, MEMORY, backtest, data, exchange, journal, risk, settings, signals, texts

AUTO_FILE = MEMORY / "trading_auto.json"
STALE = 1 / 3                    # a signal is skipped once the price went this part of the way to its target or stop
TELL_EVERY_MS = 6 * 3_600_000    # the same error is told at most every 6 hours
KEEP = 200                       # decided signals remembered


def _now() -> int:
    return int(time.time() * 1000)


def load() -> dict:
    try:
        saved = json.loads(AUTO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {"peak": saved.get("peak"), "network": saved.get("network"), "flows_from": saved.get("flows_from", _now()),
            "below": saved.get("below", False), "traded": saved.get("traded", []), "told": saved.get("told", {})}


def save(state: dict) -> None:
    now = _now()
    state["traded"] = state["traded"][-KEEP:]
    state["told"] = {key: at for key, at in state["told"].items() if now - at < TELL_EVERY_MS}
    AUTO_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTO_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def reset_peak() -> None:
    """REAL TRADE was switched on: the account stop counts from now."""
    state = load()
    state.update(peak=None, flows_from=_now(), below=False)
    save(state)


def stale(signal, mid: float) -> bool:
    """The price already went more than a third of the way from the entry to the target or to the stop."""
    gone = (mid - signal.entry) * (1 if signal.side == "long" else -1)
    if gone >= 0:
        return gone > STALE * abs(signal.target - signal.entry)
    return -gone > STALE * abs(signal.entry - signal.stop)


def _due(state: dict, key: str) -> bool:
    """True at most every 6 hours per key — an error is told that often, not at every check."""
    now = _now()
    if now - state["told"].get(key, 0) < TELL_EVERY_MS:
        return False
    state["told"][key] = now
    return True


def _trouble(state: dict, e: Exception) -> list[tuple[str, bool]]:
    text = str(e) if isinstance(e, exchange.TradingError) else texts.AUTO_NO_CONNECTION
    return [(text, True)] if _due(state, text) else []


# --- Opening ------------------------------------------------------------------------------------
def step(prepared_by_coin: dict, report: dict | None, network: str) -> list[tuple[str, bool]]:
    """A trade for each fresh signal of a checked strategy. Returns (line, say it out loud) pairs: the trades
    are said, a skipped signal only goes into the journal. A connection error leaves the signal undecided,
    so the next scan tries it again while it is still fresh."""
    state = load()
    lines: list[tuple[str, bool]] = []
    decided = {tuple(key) for key in state["traded"]}
    try:
        account, coins = exchange.account_state(network)
        for coin in COINS:
            if coin not in prepared_by_coin or coin not in coins:
                continue
            for s in signals.latest(prepared_by_coin[coin]):
                key = (s.coin, s.strategy, s.side, s.time)
                if key in decided or not backtest.is_enabled(report, coin, s.strategy):
                    continue
                lines += _trade(state, s, account, coins[coin], network)
                decided.add(key)
                state["traded"].append(list(key))
                account, coins = exchange.account_state(network)   # positions and today's loss changed
    except Exception as e:  # noqa: BLE001 — the autopilot must never stop the watch
        lines += _trouble(state, e)
    save(state)
    return lines


def _trade(state: dict, s, account: risk.AccountState, details: dict, network: str) -> list[tuple[str, bool]]:
    """One signal, decided: opened, or refused (a limit, a stale price, the exchange, an empty account) — journal
    only, except an exchange refusal or an empty perps balance, which are also said (at most every 6 hours)."""
    if account.equity <= 0:      # sir's money is not in the perps balance yet
        return [(texts.AUTO_EMPTY, _due(state, texts.AUTO_EMPTY))]
    try:
        if stale(s, details["mid"]):
            raise risk.RiskError("цената вече измина над една трета от пътя до целта или стопа.")
        plan = risk.plan(s.coin, s.side, details["mid"], s.stop, s.target, account, details["sz_decimals"],
                         details["max_leverage"], settings.limits(), network)
    except risk.RiskError as e:
        return [(texts.auto_skipped(s, str(e)), False)]
    try:
        answer = exchange.auto_place(plan)
    except exchange.TradingError as e:
        if str(e) != exchange.SENT_UNCHECKED:
            return [(texts.auto_skipped(s, str(e)), _due(state, str(e)))]
        answer = None
    except Exception:  # noqa: BLE001 — the order may be out: the guard finds the position or reconciles it
        answer = None
    if answer is None:
        journal.add_trade(plan, s.strategy, auto=True)
        return [(texts.auto_unchecked(s.coin), True)]
    if not answer.startswith("Отворих"):
        return [(texts.auto_skipped(s, answer), False)]
    journal.add_trade(plan, s.strategy, auto=True)
    return [(texts.auto_opened(plan, s.strategy), True)]


# --- Guarding -----------------------------------------------------------------------------------
def guard(network: str, account: risk.AccountState) -> list[tuple[str, bool]]:
    """At every position check while REAL TRADE is on: the account stop, then for each trade the autopilot
    opened — reconcile, stop guard, 48-hour time stop. `account` is the state the watch has just read."""
    state = load()
    lines: list[tuple[str, bool]] = []
    try:
        lines += _account_stop(state, account, network)
        now = _now()
        for t in [t for t in journal.open_trades() if t.get("auto")]:
            coin = t["coin"]
            if coin not in account.positions:   # not filled, or closed — the fills tell the result
                journal.close_trade(coin)
                continue
            said = exchange.ensure_stop(coin, network, t["stop"])
            if said:
                lines.append((said, True))
            if now - t["time"] >= signals.TIME_STOP_HOURS * data.HOUR and settings.enabled():
                if _due(state, "48h " + coin):
                    lines.append((texts.auto_time_stop(coin, t["side"]), True))
                exchange.auto_close([coin], network)
    except Exception as e:  # noqa: BLE001 — the autopilot must never stop the watch
        lines += _trouble(state, e)
    save(state)
    return lines


def _account_stop(state: dict, account: risk.AccountState, network: str) -> list[tuple[str, bool]]:
    """REAL TRADE switches itself off when the account is max_drawdown_pct below its high on two checks in a
    row (a deposit can reach the ledger a moment before the balance). Deposits and withdrawals move the
    high with them, so they are never taken for profit or loss."""
    if state["network"] != network:   # the other network is another account, with its own high
        state.update(peak=None, network=network, flows_from=_now(), below=False)
    flows, last = exchange.transfers_since(network, state["flows_from"])
    if last:
        state["flows_from"] = last + 1
    peak = account.equity if state["peak"] is None else max(state["peak"] + flows, account.equity)
    state["peak"] = peak
    below = peak > 0 and account.equity <= peak * (1 - settings.limits().max_drawdown_pct / 100)
    fire = below and state["below"]
    state["below"] = below and not fire
    if not fire:
        return []
    settings.set_enabled(False)
    trading.on_switch("real", False)
    return [(texts.account_stop(peak, account.equity), True)]
```

Note the deliberate order in `_account_stop`: the watch reads the balance first and the ledger second, so a deposit can appear in the ledger before it appears in the balance — that is why the stop needs two checks in a row below the floor.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q tests/test_trading_autopilot.py` → `26 passed`; `python -m pytest -q` → `261 passed`.

- [ ] **Step 7: Commit**

```bash
git add orion/trading/autopilot.py orion/trading/texts.py tests/conftest.py tests/test_trading_autopilot.py
git commit -m "Autopilot: trades fresh signals of checked strategies, account stop at -40 %, stop guard, 48 h time stop"
```

---

### Task 4: The REAL TRADE switch, Phantom texts, skill descriptions, persona

**Files:**
- Modify: `orion/trading/modes.py`, `orion/trading/texts.py`, `orion/trading/__init__.py`, `skills/crypto_trading_skills.py`, `app.py`, `config.py`
- Test: `tests/test_trading_modes.py`, `tests/test_trading_demo_skills.py`, `tests/test_trading_skills.py`, `tests/test_app_trading.py`

**Interfaces:**
- Consumes: `autopilot.reset_peak()`, `autopilot.load()`, `autopilot.save()` (Task 3); `confirm.ask(title, summary, body, accept) -> bool`.
- Produces: `modes.set_real(on: bool, by_button: bool = False) -> str`; `texts.autopilot_terms(limits) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_trading_modes.py` — replace the imports

```python
from orion import trading
from orion.trading import demo, modes, settings
```
with
```python
from orion import confirm, trading
from orion.trading import autopilot, demo, modes, settings
```

and replace the whole `test_real_trade_says_what_is_missing` with:

```python
def test_the_button_switches_real_trade_at_once(switched, monkeypatch):
    monkeypatch.setattr(confirm, "handler", lambda *args: pytest.fail("the button does not ask"))
    assert "не е свързан" in modes.set_real(True, by_button=True) and settings.enabled()
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    assert "Търгувам сам по проверените стратегии — 2 % риск" in modes.set_real(True, by_button=True)
    assert "Спрях истинската търговия" in modes.set_real(False) and not settings.enabled()
    assert switched == [("real", True), ("real", True), ("real", False)]


def test_real_trade_by_voice_asks_first(switched, monkeypatch):
    asked = []
    monkeypatch.setattr(confirm, "handler", lambda *args: (asked.append(args), False)[1])
    assert modes.set_real(True) == "Добре, сър — REAL TRADE остава спрян."
    assert not settings.enabled() and switched == []
    title, summary, body, accept = asked[0]
    assert title == "Автономна търговия · ТЕСТОВА МРЕЖА" and accept == "Включи"
    assert "сам, без да пита" in body and "40 %" in body
    monkeypatch.setattr(confirm, "handler", lambda *args: (asked.append(args), True)[1])
    assert "Включих REAL TRADE" in modes.set_real(True) and settings.enabled()
    assert len(asked) == 2
    modes.set_real(True)                                # already on: nothing to ask
    assert len(asked) == 2


def test_switching_off_never_asks(switched, monkeypatch):
    settings.set_enabled(True)
    monkeypatch.setattr(confirm, "handler", lambda *args: pytest.fail("off does not ask"))
    assert "Спрях" in modes.set_real(False) and not settings.enabled()


def test_switching_on_starts_the_account_stop_again(switched):
    state = autopilot.load()
    state["peak"] = 500.0
    autopilot.save(state)
    modes.set_real(True, by_button=True)
    assert autopilot.load()["peak"] is None
    state = autopilot.load()
    state["peak"] = 700.0
    autopilot.save(state)
    modes.set_real(True, by_button=True)                # already on: the count goes on
    assert autopilot.load()["peak"] == 700.0
```

`tests/test_trading_demo_skills.py` — replace `from orion import trading` with `from orion import confirm, trading`, and in `test_buttons_by_voice` after the line
`monkeypatch.setattr(trading, "on_switch", lambda name, on: switched.append((name, on)))` add:

```python
    monkeypatch.setattr(confirm, "handler", lambda *args: True)    # „включи реал трейд“ asks first
```

`tests/test_trading_skills.py` — in `test_connect_opens_the_key_dialog` replace

```python
    assert "app.hyperliquid-testnet.xyz" in cts.connect_hyperliquid()
    assert "ИСТИНСКИ" in cts.connect_hyperliquid("истински пари")
```
with
```python
    testnet, mainnet = cts.connect_hyperliquid(), cts.connect_hyperliquid("истински пари")
    assert "app.hyperliquid-testnet.xyz" in testnet and "Phantom" in testnet
    assert "ИСТИНСКИ" in mainnet and "Phantom" in mainnet and "Trust" not in testnet + mainnet
```

`tests/test_app_trading.py` — replace the imports

```python
import app
from orion.trading import exchange, settings
```
with
```python
import pytest

import app
from orion import confirm
from orion.trading import exchange, settings
```

and in `test_the_two_trading_buttons` replace

```python
    api.set_real_trading(False)
    assert not settings.enabled() and "Спрях истинската търговия" in said[-1]
```
with
```python
    api.set_real_trading(False)
    assert not settings.enabled() and "Спрях истинската търговия" in said[-1]
    monkeypatch.setattr(confirm, "handler", lambda *args: pytest.fail("the button does not ask"))
    api.set_real_trading(True)
    assert settings.enabled() and "Включих REAL TRADE" in said[-1]
    api.set_real_trading(False)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q tests/test_trading_modes.py tests/test_trading_demo_skills.py tests/test_trading_skills.py tests/test_app_trading.py`
Expected: FAIL — `TypeError: set_real() got an unexpected keyword argument 'by_button'`, the connect test (no „Phantom“), the voice test (no dialog).

- [ ] **Step 3: Implement**

`orion/trading/texts.py` — replace the whole `CONNECT_STEPS = {…}` and `MAINNET_WARNING = (…)` definitions with:

```python
CONNECT_STEPS = {
    "testnet": ("Отворих прозореца за ключа. Стъпките: отворете app.hyperliquid-testnet.xyz и свържете Phantom "
                "(Connect → Phantom); после More → API — натиснете Generate и одобрете в Phantom; накрая поставете "
                "Ethereum адреса си от Phantom (0x…) и API ключа в прозореца. Никога не поставяйте думите за "
                "възстановяване."),
    "mainnet": ("Отворих прозореца за ключа за ИСТИНСКИ пари. Стъпките: в Phantom внесете пари в Perps баланса; "
                "отворете app.hyperliquid.xyz и свържете Phantom (Connect → Phantom); More → API — Generate и "
                "одобрете в Phantom; поставете Ethereum адреса си от Phantom (0x…) и API ключа в прозореца. Този "
                "ключ може само да търгува — не може да тегли пари, и важи до 180 дни. Никога не поставяйте "
                "думите за възстановяване."),
}
MAINNET_WARNING = ("От сега REAL TRADE търгува с ИСТИНСКИ пари: Орион отваря и затваря сделки сам по проверените "
                   "стратегии. Лимитите остават (2 % риск на сделка, до 10x, до 6 % загуба на ден, до 3 позиции), "
                   "а при спад от 40 % от най-високата стойност на сметката REAL TRADE се спира сам. Загубите ще "
                   "са истински.")


def autopilot_terms(limits) -> str:
    """The body of the dialog before REAL TRADE is switched on by voice."""
    return "\n".join([
        "Орион отваря и затваря сделки сам, без да пита — само по проверените стратегии.",
        f"Риск {limits.risk_pct:g} % на сделка, до {limits.max_leverage}x, до {limits.daily_loss_pct:g} % загуба "
        f"на ден, до {limits.max_positions} позиции.",
        f"Ако сметката падне с {limits.max_drawdown_pct:g} % от най-високата си стойност, REAL TRADE се спира сам.",
        "Стопът и целта на всяка сделка са в борсата.",
    ])
```

`orion/trading/modes.py` — replace

```python
from .. import trading
from . import demo, settings
```
with
```python
from .. import confirm, trading
from . import autopilot, demo, settings, texts
```

and replace the whole `set_real` with:

```python
def set_real(on: bool, by_button: bool = False) -> str:
    """REAL TRADE: while it is on, the autopilot trades the real account by itself. The window button switches
    it at once (the click is sir's decision); by voice or chat a dialog asks first — the microphone hears the
    TV. Switching off never asks. Each switch from off to on starts the account stop's count again."""
    network = settings.network()
    where = "тестовата мрежа" if network == "testnet" else "ИСТИНСКИ пари"
    was_on = settings.enabled()
    if on and not was_on and not by_button:
        title = f"Автономна търговия · {'ТЕСТОВА МРЕЖА' if network == 'testnet' else 'РЕАЛНИ ПАРИ'}"
        if not confirm.ask(title, f"Орион търгува сам ({where})", texts.autopilot_terms(settings.limits()),
                           "Включи"):
            return "Добре, сър — REAL TRADE остава спрян."
    settings.set_enabled(on)
    trading.on_switch("real", bool(on))
    if not on:
        return ("Спрях истинската търговия — няма да отварям истински сделки. Отворените позиции остават със "
                "стоповете си.")
    if not was_on:
        autopilot.reset_peak()
    if not settings.account(network):
        return f"Включих REAL TRADE ({where}), но Hyperliquid не е свързан — кажете „свържи Hyperliquid“."
    return (f"Включих REAL TRADE ({where}). Търгувам сам по проверените стратегии — "
            f"{settings.limits().risk_pct:g} % риск на сделка, стоп и цел в борсата. Ще Ви казвам за всяка сделка.")
```

`app.py` — replace

```python
    def set_real_trading(self, enabled: bool):
        """REAL TRADE — the real Hyperliquid account (every trade with approval)."""
        self._app.say(trading_modes.set_real(bool(enabled)))
```
with
```python
    def set_real_trading(self, enabled: bool):
        """REAL TRADE — Orion trades the real Hyperliquid account by itself; the click is sir's decision."""
        self._app.say(trading_modes.set_real(bool(enabled), by_button=True))
```

`skills/crypto_trading_skills.py`:
- module docstring: replace
  `(DEMO TEST); всяка истинска сделка чака „Одобри“ от сър (REAL TRADE).`
  with
  ```
  (DEMO TEST); с REAL TRADE търгува сам и истинската сметка (Phantom Perps) по проверените стратегии, а сделките,
  които сър поиска, чакат „Одобри“.
  ```
- replace
  ```python
  NEITHER = ("Включете DEMO TEST за демо сделки (без истински пари) или REAL TRADE за истински — с Вашето „Одобри“ "
             "за всяка сделка.")
  ```
  with
  ```python
  NEITHER = ("Включете DEMO TEST за демо сделки (без истински пари) или REAL TRADE за истински — сделките, които "
             "поискате, пак чакат Вашето „Одобри“.")
  ```
- `connect_hyperliquid` docstring first line → `"""Свързва Орион с Hyperliquid (където Phantom търгува Perps): отваря прозореца за API ключа.`
- `resume_trading` docstring → 
  ```python
      """Пуска истинската търговия (бутона REAL TRADE): Орион търгува сам по проверените стратегии — първо пита в
      прозорец."""
  ```
- in `switch_trading_network` replace `return "Минах на истински пари. Всяка сделка пак чака Вашето „Одобри“." + extra` with
  `return "Минах на истински пари. С включен REAL TRADE търгувам сам по проверените стратегии." + extra`
- `set_real_trading` docstring first line → 
  ```python
      """Включва или спира REAL TRADE — Орион търгува сам истинската сметка в Hyperliquid (Phantom Perps) по
      проверените стратегии; включването първо пита в прозорец.
  ```
  (the `Args:` part stays; `set_real_trading` and `resume_trading` keep calling `modes.set_real(...)` without `by_button`, so they ask).

`config.py` (persona, one line) — replace
`сделки — open_trade и close_trade (сър одобрява всяка в прозорец).`
with
`сделки, които сър поиска — open_trade и close_trade (сър одобрява всяка в прозорец); с включен REAL TRADE търгуваш и сам по проверените стратегии и казваш за всяка сделка.`

`orion/trading/__init__.py` — replace the docstring paragraph

```
Design: docs/superpowers/specs/2026-10-03-crypto-trading-design.md. Every number (signals, backtest,
risk) is computed in code; the language model only explains it. Every real order needs sir's „Одобри“,
enforced in orion/trading/exchange.py.
```
with
```
Design: docs/superpowers/specs/2026-10-03-crypto-trading-design.md and 2026-10-03-autonomous-trading-design.md.
Every number (signals, backtest, risk) is computed in code; the language model only explains it. A real order
a skill asks for needs sir's „Одобри“ (orion/trading/exchange.py); while REAL TRADE is on, the autopilot
(orion/trading/autopilot.py) trades the checked strategies by itself within the hard limits.
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q` → `264 passed`. Check: `grep -rn "Trust" orion skills app.py config.py` → no output.

- [ ] **Step 5: Commit**

```bash
git add orion/trading/modes.py orion/trading/texts.py orion/trading/__init__.py skills/crypto_trading_skills.py app.py config.py tests/test_trading_modes.py tests/test_trading_demo_skills.py tests/test_trading_skills.py tests/test_app_trading.py
git commit -m "REAL TRADE switch: the button at once, voice asks first; Phantom connect steps; Trust Wallet removed"
```

---

### Task 5: The watch runs the autopilot

**Files:**
- Modify: `orion/trading/watcher.py`
- Test: `tests/test_trading_watcher.py`

**Interfaces:**
- Consumes: `autopilot.step(prepared, report, network)`, `autopilot.guard(network, account)` (Task 3); `journal.open_trades()` (Task 1).
- Produces: `Watcher.tell(lines: list[tuple[str, bool]]) -> None`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_trading_watcher.py` replace the import line

```python
from orion.trading import backtest, data, demo, exchange, journal, lab, market, practice, risk, settings, signals, watcher
```
with
```python
from orion.trading import (autopilot, backtest, data, demo, exchange, journal, lab, market, practice, risk, settings,
                           signals, watcher)
```

In `test_positions_chip_fills_and_time_stop`, after `monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))` add:

```python
    monkeypatch.setattr(autopilot, "guard", lambda network, account: [])
```

Append:

```python


# --- The autopilot (REAL TRADE with a key) ---------------------------------------------------------
def test_with_a_key_the_autopilot_trades_instead_of_the_alert(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    calls = []
    monkeypatch.setattr(autopilot, "step", lambda prepared, report, network: (
        calls.append((sorted(prepared), report, network)),
        [("Отворих лонг на биткойн — пробив.", True), ("Пропуснах сигнал за шорт на етериум.", False)])[1])
    w, said, hud = make()
    world["BTC"] = [sig(1)]
    w.scan()
    assert calls == [(["BTC", "ETH", "SOL"], REPORT, "testnet")]
    assert said == ["Отворих лонг на биткойн — пробив."]
    assert ("addLog", ("trading", "Пропуснах сигнал за шорт на етериум.")) in hud
    assert journal.record(days=1)["open"] == 1                 # the signal is still in the journal


def test_no_autopilot_while_real_trade_is_off_or_in_test_mode(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    monkeypatch.setattr(autopilot, "step", lambda *args: pytest.fail("no autopilot"))
    monkeypatch.setattr(exchange, "blocked", True)
    make()[0].scan()
    monkeypatch.setattr(exchange, "blocked", False)
    settings.set_enabled(False)
    make()[0].scan()


def test_the_guard_runs_at_every_position_check_while_real_trade_is_on(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    state = risk.AccountState(1000.0)
    monkeypatch.setattr(exchange, "account_state", lambda network: (state, {}))
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [])
    seen = []
    monkeypatch.setattr(autopilot, "guard", lambda network, account: (
        seen.append((network, account)), [("Затварям лонг на биткойн — изтекоха 48 часа.", True)])[1])
    w, said, hud = make()
    w.positions()
    assert seen == [("testnet", state)] and said == ["Затварям лонг на биткойн — изтекоха 48 часа."]
    settings.set_enabled(False)
    w.positions()
    assert len(seen) == 1


def test_the_48_hour_reminder_is_only_for_sirs_own_trades(world, monkeypatch):
    monkeypatch.setattr(settings, "account", lambda network: ("0xme", "0xkey"))
    monkeypatch.setattr(autopilot, "guard", lambda network, account: [])
    state = risk.AccountState(1000.0, {"BTC": {"side": "long", "size": 0.01, "entry": 84000.0, "pnl": 0.0,
                                               "liq": 0.0, "value": 840.0}})
    monkeypatch.setattr(exchange, "account_state", lambda network: (state, {}))
    monkeypatch.setattr(exchange, "fills_since", lambda network, since: [])
    w, said, hud = make()
    monkeypatch.setattr(journal, "_now", lambda: int(w.clock.now * 1000))
    plan = risk.OrderPlan("BTC", "long", 0.01, 84000.0, 83000.0, 86000.0, 2, 840.0, 420.0, 10.0, 20.0, 0.0, 0.8,
                          "testnet")
    journal.add_trade(plan, "пробив", auto=True)
    w.clock.now += 49 * 3600
    w.positions()
    assert not any("48 часа" in s for s in said)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q tests/test_trading_watcher.py`
Expected: 3–4 FAIL (`step`/`guard` never called; the reminder is said for the autopilot's trade).

- [ ] **Step 3: Implement in `orion/trading/watcher.py`**

Replace the module docstring's first paragraph (up to "…shows the real positions and the demo accounts.") with:

```python
The background watch (own thread, started by app.py). Every 15 minutes it fetches the three coins once and
uses them for everything: each new signal goes into the journal; with REAL TRADE on and a key connected, the
autopilot trades the checked strategies by itself (autopilot.step — voice 08:00–23:00, journal always);
REAL TRADE on without a key announces a strong signal of a checked strategy instead; with DEMO TEST on, the
demo accounts and the practice account trade by themselves (journal only). With a key connected it checks
the real account (every minute while positions are open, else every 5): closed trades, the autopilot's
guard (account stop, stops, its 48-hour time stop) and the 48-hour reminder for sir's own trades. The
top-bar chip shows the real positions and the demo accounts.
```
(keep the following sentence about the sandbox lock).

Replace the import

```python
from . import COINS, NAMES, backtest, data, demo, exchange, journal, lab, market, practice, settings, signals, texts
```
with
```python
from . import (COINS, NAMES, autopilot, backtest, data, demo, exchange, journal, lab, market, practice, settings,
               signals, texts)
```

Replace the beginning of `scan()` (through the alert loop)

```python
    def scan(self) -> None:
        report = backtest.load()
        options = settings.load()
        prepared = {coin: market.live(coin) for coin in COINS}
        for p in prepared.values():
            for s in signals.latest(p):
                if (journal.add_signal(s, "watch") and options["enabled"]
                        and self._worth(s, report, options["announce_strength"])):
                    self.announce(texts.signal_alert(s, report))
```
with
```python
    def scan(self) -> None:
        report = backtest.load()
        options = settings.load()
        network = settings.network()
        auto = bool(options["enabled"] and settings.account(network)) and not exchange.blocked
        prepared = {coin: market.live(coin) for coin in COINS}
        for p in prepared.values():
            for s in signals.latest(p):
                if (journal.add_signal(s, "watch") and options["enabled"] and not auto
                        and self._worth(s, report, options["announce_strength"])):
                    self.announce(texts.signal_alert(s, report))
        if auto:
            self.tell(autopilot.step(prepared, report, network))
```
(the `if options["demo"]:` block and `data.record_open_interest(...)` stay after it).

Right above `def announce(self, text: str) -> None:` add:

```python
    def tell(self, lines: list[tuple[str, bool]]) -> None:
        """The autopilot's lines: (text, say it out loud) — the rest go into the journal only."""
        for text, loud in lines:
            if loud:
                self.announce(text)
            else:
                self.hud("addLog", "trading", text)

```

At the end of `positions()` replace

```python
        now_ms = self.clock() * 1000
        for coin in state.positions:
            opened = journal.open_trade_time(coin)
            if opened and coin not in self.time_stop_told and now_ms - opened >= signals.TIME_STOP_HOURS * data.HOUR:
                self.time_stop_told.add(coin)
                name = NAMES.get(coin, coin).lower()
                self.announce(f"Сър, сделката в {name} е отворена от 48 часа — времето ѝ изтече. Кажете "
                              f"„затвори {name}“ и ще я затворя след Вашето одобрение.")
```
with
```python
        now_ms = self.clock() * 1000
        newest = {t["coin"]: t for t in journal.open_trades()}   # the autopilot closes its own trades itself
        for coin in state.positions:
            trade = newest.get(coin)
            if (trade and not trade.get("auto") and coin not in self.time_stop_told
                    and now_ms - trade["time"] >= signals.TIME_STOP_HOURS * data.HOUR):
                self.time_stop_told.add(coin)
                name = NAMES.get(coin, coin).lower()
                self.announce(f"Сър, сделката в {name} е отворена от 48 часа — времето ѝ изтече. Кажете "
                              f"„затвори {name}“ и ще я затворя след Вашето одобрение.")
        if settings.enabled() and not exchange.blocked:
            self.tell(autopilot.guard(network, state))
```

(`journal.open_trade_time` stays in `journal.py` — tests and skills still use it.)

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q tests/test_trading_watcher.py` → `14 passed`; `python -m pytest -q` → `268 passed`.

- [ ] **Step 5: Commit**

```bash
git add orion/trading/watcher.py tests/test_trading_watcher.py
git commit -m "Watch: the autopilot trades at each scan and guards at each position check"
```

---

### Task 6: Code Orion writes itself cannot reach trading

**Files:**
- Modify: `orion/self_improve.py`
- Test: `tests/test_self_improve_trading.py` (new)

**Interfaces:**
- Produces: `self_improve.TRADING_BAN: str`; `validate_skill_code` adds `TRADING_BAN` to the problems of any code that imports `orion.trading…` (also inside functions), `from orion import trading`, or uses the attribute `orion.trading`.

Side effect worth knowing: test mode's `_fix_code` already refuses to rewrite a file whose current code has problems — so `skills/crypto_trading_skills.py` (which imports `orion.trading`) can no longer be rewritten by test mode either. Docstring-only rewrites (AST-proven identical) are a different path and keep working.

- [ ] **Step 1: Write the failing test**

Create `tests/test_self_improve_trading.py`:

```python
import pytest

from orion.self_improve import TRADING_BAN, validate_skill_code

SKILL = """from orion import orion_tool
{imports}


@orion_tool
def my_skill(text: str) -> str:
    \"\"\"Прави нещо.\"\"\"
{body}
    return text
"""


def problems(imports="", body=""):
    return validate_skill_code(SKILL.format(imports=imports, body=body), set())[0]


@pytest.mark.parametrize("imports, body", [
    ("from orion.trading import exchange", "    exchange.auto_place(None)"),
    ("from orion.trading.autopilot import step", "    step({}, None, 'mainnet')"),
    ("import orion.trading.modes", "    orion.trading.modes.set_real(True)"),
    ("from orion import trading", "    trading.on_switch('real', True)"),
    ("import orion", "    orion.trading.settings.set_enabled(True)"),
    ("", "    from orion.trading import settings\n    settings.set_enabled(True)"),
])
def test_code_orion_writes_may_not_reach_trading(imports, body):
    assert TRADING_BAN in problems(imports, body)


def test_other_orion_modules_are_still_fine():
    assert problems("from orion import markets", "    markets.analyze") == []
    assert TRADING_BAN not in problems("import json", "    json.dumps({'trading': 1})")
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest -q tests/test_self_improve_trading.py`
Expected: FAIL — `ImportError: cannot import name 'TRADING_BAN'`.

- [ ] **Step 3: Implement in `orion/self_improve.py`**

After `FORBIDDEN_MODULES = {"importlib", "ctypes", "winreg", "pickle", "marshal"}` add:

```python
# REAL TRADE trades real money by itself — code Orion writes may not reach the trading package at all.
TRADING_BAN = "Търговията (orion.trading) е забранена за умения, които пиша сам — там се търгува с истински пари."
```

At the end of `validate_skill_code` replace

```python
    problems += _undefined_names(code)
    return list(dict.fromkeys(problems)), sorted(set(warnings)), [fn.name for fn in tools]
```
with
```python
    if _reaches_trading(tree):
        problems.append(TRADING_BAN)
    problems += _undefined_names(code)
    return list(dict.fromkeys(problems)), sorted(set(warnings)), [fn.name for fn in tools]


def _reaches_trading(tree: ast.AST) -> bool:
    """Any import of orion.trading (also inside functions) or the attribute orion.trading."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(a.name.split(".")[:2] == ["orion", "trading"] for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and n.module:
            parts = n.module.split(".")
            if parts[:2] == ["orion", "trading"] or (n.module == "orion" and any(a.name == "trading" for a in n.names)):
                return True
        if (isinstance(n, ast.Attribute) and n.attr == "trading" and isinstance(n.value, ast.Name)
                and n.value.id == "orion"):
            return True
    return False
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q tests/test_self_improve_trading.py` → `7 passed`; `python -m pytest -q` → `275 passed`.
Check that no skill Orion wrote itself is now rejected: `grep -ln "orion.trading\|import trading" skills/*.py` → only `skills/crypto_trading_skills.py` (written by hand, not by Orion).

- [ ] **Step 5: Commit**

```bash
git add orion/self_improve.py tests/test_self_improve_trading.py
git commit -m "Self-improve: code Orion writes may not import orion.trading"
```

---

### Task 7: The window and the README

**Files:**
- Modify: `web/src/components/Console.jsx`, `web/src/components/KeyDialog.jsx`, `README.md`
- Test: `web/src/components/Modes.test.jsx`, `web/src/components/Trading.test.jsx`
- Rebuild: `ui/` (`npm run build`)

- [ ] **Step 1: Write the failing tests**

`web/src/components/Modes.test.jsx` — after the test `'the console has Demo test and Real trade next to Test mode'` add:

```jsx
  it('Real trade says that Orion trades by itself', () => {
    const { getByLabelText } = render(<Console />);
    expect(getByLabelText('Real trade').closest('label').title).toMatch(/Phantom Perps\): Orion trades by itself/);
  });
```

`web/src/components/Trading.test.jsx` — in `'the key goes to Python through its own call, never through the chat'`, after `expect(getByText('Hyperliquid · TESTNET')).toBeTruthy();` add:

```jsx
    expect(getByLabelText(/Wallet address \(Phantom — Ethereum/)).toBeTruthy();
```

- [ ] **Step 2: Run them to see them fail**

Run (in `web/`): `npx vitest run`
Expected: 2 failed, 49 passed.

- [ ] **Step 3: Implement**

`web/src/components/Console.jsx` — replace

```jsx
    title: 'The real Hyperliquid account: forecasts when you ask, every trade only after you approve it' },
```
with
```jsx
    title: 'The real Hyperliquid account (Phantom Perps): Orion trades by itself within the limits' },
```

`web/src/components/KeyDialog.jsx` — replace `        Wallet address (Trust Wallet)` with `        Wallet address (Phantom — Ethereum, 0x…)`.

`README.md` (section „Crypto forecasts and trading (Hyperliquid)“):
- replace
  ```
  Orion forecasts and trades **Bitcoin, Ethereum and Solana** on Hyperliquid — the exchange behind Trust
  Wallet's "Perps" tab. Every number comes from code (`orion/trading/`); the language model only reads it out.
  ```
  with
  ```
  Orion forecasts and trades **Bitcoin, Ethereum and Solana** on Hyperliquid — the exchange behind Phantom's
  "Perps" tab (the perps account of Phantom's Ethereum address). Every number comes from code
  (`orion/trading/`); the language model only reads it out.
  ```
- replace
  ```
  - „Отвори лонг на биткойн“, „Затвори етериума“, „Затвори всички позиции“ — every open and close shows an
    approval dialog with every number; nothing happens without „Одобри“.
  ```
  with
  ```
  - „Отвори лонг на биткойн“, „Затвори етериума“, „Затвори всички позиции“ — a trade you ask for shows an
    approval dialog with every number; nothing happens without „Одобри“.
  ```
- replace the whole **Connecting (once).** paragraph with:
  ```
  **Connecting (once).** In Phantom, deposit into the Perps balance (from SOL or USDC). Say „Свържи
  Hyperliquid за истински пари“ → open app.hyperliquid.xyz, Connect → Phantom, More → API → Generate → approve in
  Phantom → paste Phantom's Ethereum address (0x…) and the API key into Orion's dialog. The key trades but cannot
  withdraw and is valid up to 180 days. „Мини на истински пари“ (with its warning dialog) moves from the testnet
  to real money.
  ```
- in the **Three buttons** paragraph replace
  ```
  testnet order check. **Real trade** is the real Hyperliquid account: forecasts and advice when you ask, every
  trade only after „Одобри“; off means no real orders.
  ```
  with
  ```
  testnet order check. **Real trade** is the real account, and Orion trades it **by itself**: every 15 minutes
  a fresh signal of a checked strategy is opened with its stop and target on the exchange (2 % risk, the limits
  above), closed after 48 hours at the latest, and each trade is announced (voice 08:00–23:00, journal always).
  A signal it skips (a limit, the price already moved) goes into the journal. If the account falls 40 % below its
  high (deposits and withdrawals do not count), Real trade switches itself off. The button switches it on at
  once; „включи реал трейд“ by voice asks first; off is always immediate. Trades you ask for still need
  „Одобри“, code Orion writes itself cannot reach the trading modules, and with Orion closed no new trades are
  opened (the stops on the exchange still work).
  ```

- [ ] **Step 4: Run the tests and build**

Run in `web/`: `npx vitest run` → `50 passed`; `npm run build` → `✓ built`.
Run from the **PowerShell** tool in the project root: `python web\e2e\run.py` → `passed 37, failed 0`.
Check: `grep -rn "Trust" web/src README.md orion skills` → no output.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/Console.jsx web/src/components/KeyDialog.jsx web/src/components/Modes.test.jsx web/src/components/Trading.test.jsx README.md ui/
git commit -m "Window and README: Real trade trades by itself, Phantom wallet address"
```
(If `git status` shows `ui/index.html` or `ui/assets/style.css` with line-ending-only changes, they are harmless; `git add ui/` normalises them.)

---

### Task 8: The live check on sir's real account (only with sir, only when he says)

No code. Every step needs sir present; the order matters. Stop and tell sir if any step does not give the expected result.

- [ ] **Step 1: Sir connects Phantom** (if not done): deposit into Phantom's Perps balance (≥ 15 $ is enough for the check; the autopilot needs ~50 $+ to place a 2 % trade above Hyperliquid's 10 $ minimum), then in Orion „свържи Hyperliquid за истински пари“ → app.hyperliquid.xyz → Connect → Phantom → More → API → Generate → approve in Phantom → paste the address and key. Orion answers „Свързах се с Hyperliquid в истинската мрежа. В сметката има … долара.“

- [ ] **Step 2: Read-only probe** — write `probe.py` in the scratchpad (not in the repo) and run it from the project root (`python <scratchpad>/probe.py` with the project root as the working directory):

```python
import sys
sys.path.insert(0, ".")
from orion.trading import exchange

info, _, address = exchange.client_factory("mainnet")
state = info.user_state(address)
print("perps accountValue:", state["marginSummary"]["accountValue"])
print("spot balances:", [(b["coin"], b["total"]) for b in info.spot_user_state(address)["balances"]])
ledger = info.user_non_funding_ledger_updates(address, 0)
print("ledger types:", sorted({e["delta"]["type"] for e in ledger}))
for entry in ledger[-5:]:
    print(entry["time"], entry["delta"])
print("counted by perp_flow:", exchange.transfers_since("mainnet", 0))
```

Expected: `accountValue` ≈ the Perps balance Phantom shows; the ledger types are among those `perp_flow` knows (`deposit`, `withdraw`, `accountClassTransfer`, `internalTransfer`, `subAccountTransfer`, `vaultDeposit`, `vaultWithdraw`, `send`); `counted by perp_flow` ≈ the money sir moved into perps.
**If `accountValue` is 0 while Phantom shows a Perps balance** (the money sits in spot / a unified account) or a ledger type moving USDC is unknown: STOP — tell sir, then fix `exchange.account_state` / `exchange.perp_flow` with a failing test first (TDD) before anything trades.

- [ ] **Step 3: The smallest real order** (≈11 $ BTC long, stop and target checked, closed at once, ≈1 cent fees) — only after sir says „да“:

```bash
python -c "import sys; sys.path.insert(0, '.'); from orion.trading import exchange; print(exchange.smallest_check('mainnet'))"
```

Expected: `Проверката в истинската сметка мина: входът, стопът и целта се поставиха и позицията се затвори.` — and the trade shows in Phantom's Perps history.

- [ ] **Step 4: Restart Orion and switch on** — close Orion and open it from the desktop icon (the new code loads only on start). Sir says „мини на истински пари“ (warning dialog → „Мини на истински пари“) and presses **Real trade** in the window. Orion: „Включих REAL TRADE (ИСТИНСКИ пари). Търгувам сам по проверените стратегии — 2 % риск…“.

- [ ] **Step 5: Finish the branch** — use superpowers:finishing-a-development-branch (merge into `main` or keep the branch — sir's choice; push only if sir asks).

---

## Self-review (done while writing)

- **Spec coverage:** autonomy on REAL TRADE (Tasks 3, 5); checked strategies only, signal's own levels, 2 % risk (Task 3); stale skip (Task 3); one decision per signal (Task 3); 48 h time stop for auto trades + reminder only for sir's (Tasks 3, 5); announcements voice/journal (Tasks 3, 5); skipped signals journal-only (Task 3); account stop −40 % with deposits/withdrawals excluded and reset on switch-on (Tasks 2, 3, 4); stop guard (Tasks 2, 3); reconcile (Task 3); button vs voice switch-on, off never asks (Task 4); voice trades keep „Одобри“ (unchanged `place`/`close`, Task 2 keeps them); Orion-written code banned (Task 6); test mode blocked (Tasks 2, 5); errors once per 6 h (Task 3); Phantom texts, key dialog, README, persona, Trust Wallet removed (Tasks 4, 7); live check ≈11 $ only on sir's word (Tasks 2, 8).
- **Spec deviations (small, deliberate):** `auto_close(coins, network)` has no `reason` (the reason is the autopilot's own line); the account stop needs two checks in a row (a deposit can reach the ledger before the balance); a perps balance of 0 is said aloud once per 6 h (`AUTO_EMPTY`) instead of journal-only; each network keeps its own high.
- **Types:** `step`/`guard` return `list[tuple[str, bool]]` everywhere; `Watcher.tell` consumes exactly that; `transfers_since` returns `(float, int)`; `set_real(on, by_button=False)`.
