# Orion — autonomous real trading through Phantom Perps (sub-project A3)

Date: 2026-10-03 · Status: approved in conversation (sir: „искам да се махне трейдинга с тръст валлет и да се
продължи по този план“). Builds on `2026-10-03-crypto-trading-design.md` and `2026-10-03-demo-trading-design.md`.
It replaces two of their rules: real trades no longer all need „Одобри“ (the autopilot's trades do not), and the
wallet is Phantom, not Trust Wallet. The older specs and plans stay as they are — they record what was decided then.

## Why

Sir: „искам орион да може да търгува изцяло автономно през phantom wallet … без аз да правя нещо, доверявам му
се, поемам риска и тези пари не влизат в бюджета ми … натисна ли реал трейд той да може да трейдва там, има perps
… лонг и шорт позиции“. Phantom's Perps tab runs on Hyperliquid: the perps account is tied to the wallet's
Ethereum address, and the same account works on app.hyperliquid.xyz ([Phantom Help](https://help.phantom.com/hc/en-us/articles/42292249388307-Trade-perps-in-Phantom),
[The Block](https://www.theblock.co/post/361533/phantom-wallet-perp-trading-hyperliquid)). So the existing
Hyperliquid code already reaches Phantom's perps account — what changes is who decides: Orion, within hard limits.
Money is deposited from Phantom's Solana side (SOL/USDC) and bridged by Phantom; Orion never moves money.

## Decisions (sir's choices)

| Question | Choice |
|---|---|
| Autonomy | REAL TRADE on = Orion opens and closes real trades by itself, no „Одобри“ |
| Wallet | Phantom (its Perps = the Hyperliquid account of Phantom's Ethereum address). Trust Wallet is removed from Orion's texts, the key dialog and the README |
| Who decides a trade | Only the strategies that pass the honest check (`backtest.is_enabled`) — today breakout on BTC and ETH. The language model never decides a trade |
| Risk per trade | 2 % of the account at the stop (unchanged); ≤10x, ≤6 % lost per day, ≤3 open positions (unchanged) |
| Account stop | The account falls 40 % from its high → Orion switches REAL TRADE off itself and says so; open positions keep their stops |
| Start | Straight to real money. The first live check is the smallest trade (≈11 $) in the real account — only when sir says |
| Trades sir asks for by voice/chat | Still behind „Одобри“ (the microphone hears the TV) |
| Switching REAL TRADE on | The window button: at once (the click is the decision). By voice: a confirmation dialog. Off: always at once |
| Approach | Extend the existing Hyperliquid code. Not the Phantom MCP server (separate process, Phantom login, its docs ask agents to confirm trades, +0.05 % Phantom fee); not Drift/Jupiter (another exchange, not Phantom's Perps tab) |

What sir heard before choosing: the 365-day simulation of breakout BTC+ETH at 2 % risk gave +17.8 % with a 32 %
drawdown on the way (1 % risk: +12.1 %, drawdown 17 %); the edge is thin.

## What sir sees and says

- **Setup, once (sir):** in Phantom, deposit into the Perps balance (from SOL or USDC) → app.hyperliquid.xyz →
  Connect → Phantom → More → API → Generate → approve in Phantom → tell Orion „свържи Hyperliquid за истински
  пари“ → paste Phantom's Ethereum address (0x…) and the API key into the dialog. The key can trade, not
  withdraw, and is valid up to 180 days. Orion never asks for the recovery phrase (the existing guard stays).
- **„Мини на истински пари“** → the existing warning dialog; its text now says Orion trades by itself, the limits
  and the account stop.
- **REAL TRADE switched on with the button** → „Включих REAL TRADE (ИСТИНСКИ пари). Търгувам сам по проверените
  стратегии — 2 % риск на сделка, стоп и цел в борсата. Ще Ви казвам за всяка сделка.“ (testnet: „тестовата
  мрежа“; no key: the existing „Hyperliquid не е свързан — кажете „свържи Hyperliquid““).
- **„Включи реал трейд“ by voice** → dialog „Автономна търговия · РЕАЛНИ ПАРИ“ with the limits and the account
  stop → button „Включи“; „Откажи“ → „Добре, сър — REAL TRADE остава спрян.“
- **Every trade, journal always, voice 08:00–23:00** (the existing voice hours):
  „Отворих лонг на биткойн — пробив: 0.0012 BTC (≈ 74 $), 4x, стоп 61 200, цел 64 800. Рискът е 2.00 $.“ /
  „Затворих лонг на биткойн: +4.10 $.“ (every close — target, stop, time stop — is told once, from the fills, as
  today). A close Orion makes itself is preceded by why: „Затварям шорт на етериум — изтекоха 48 часа.“
- **A signal Orion did not take** → one journal line, no voice: „Пропуснах сигнал в биткойн: <reason>.“ (a limit,
  the price already moved, below Hyperliquid's 10 $ minimum, not enough margin).
- **Account stop** (journal always, voice in the voice hours): „Сър, сметката падна с 40 % от най-високата си
  стойност (от 250 $ на 150 $). Спрях REAL TRADE — отворените позиции остават със стоповете си. Пуснете бутона
  пак, когато решите.“
- **Errors** (exchange refused, the key expired, no connection for a while): journal + voice, at most once per
  6 hours per kind; REAL TRADE stays on and Orion keeps trying.
- **Voice/chat trades** („отвори лонг на биткойн“, „затвори етериума“, „стоп на входа“) work as today, with
  „Одобри“.
- **The window:** the REAL TRADE switch's tooltip becomes „The real Hyperliquid account (Phantom Perps): Orion
  trades by itself within the limits“; the key dialog says „Wallet address (Phantom — Ethereum, 0x…)“. The top
  chip shows the real positions as today.

## How it works

### `orion/trading/autopilot.py` (new)

State in `memory/trading_auto.json` (test mode's sandbox redirects `memory/*.json`):
`{"peak": float | null, "flows_from": ms, "traded": [[coin, strategy, side, signal_time], …] (last 200),
"told": {kind: ms}}`.

- **`step(prepared_by_coin, report, network) -> list[str]`** — called by the watch's scan (every 15 min) while
  REAL TRADE is on, a key is connected and the exchange is not blocked. Returns the lines to announce.
  1. `state, coins = exchange.account_state(network)`.
  2. For each coin, for each `s` in `signals.latest(prepared[coin])` with `backtest.is_enabled(report, coin,
     s.strategy)` whose key `(coin, strategy, side, time)` is not in `traded`:
     - **Stale check:** `mid = coins[coin]["mid"]`; skip if the price has already gone more than 1/3 of the way
       from `s.entry` to `s.target`, or more than 1/3 of the way to `s.stop`.
     - **Plan:** `risk.plan(coin, s.side, mid, s.stop, s.target, state, sz_decimals, max_leverage,
       settings.limits(), network)` — the stop and target are the signal's own levels (what the backtest
       measured); the size is computed from the current price to the stop, so the risk stays 2 %.
     - **Send:** `exchange.auto_place(plan)`; on success `journal.add_trade(plan, s.strategy, auto=True)`, the
       line, and `state` is read again (positions and today's loss changed).
     - The key goes into `traded` after a definite outcome (placed, refused by a limit, stale, not filled). A
       connection error does not mark it, so the next scan retries while the signal is still fresh.
- **`guard(network) -> list[str]`** — called by the watch's position check (every minute while positions are
  open, else every 5 minutes) while REAL TRADE is on:
  - **Account stop:** `flows = exchange.transfers_since(network, flows_from)` (non-trading USDC moved into (+)
    or out of (−) the perps account since the last check); `peak = max(peak + flows, equity)` (first time:
    `equity`); if `equity <= peak × (1 − max_drawdown_pct / 100)` → `modes.set_real(False)` plus the
    account-stop line. Deposits and withdrawals therefore never look like profit or loss.
  - **Stop guard:** for each open position Orion opened (an open `auto` trade in the journal for that coin):
    `exchange.ensure_stop(coin, network, trade["stop"])` — a stop exists → nothing; missing → placed at the
    journal's stop; still missing → closed at market and said.
  - **Time stop:** an `auto` trade open ≥48 hours → the line „Затварям … — изтекоха 48 часа.“ and
    `exchange.auto_close([coin], network)`; the result („Затворих …: −0.80 $“) comes from the fills like every
    other close, so nothing is said twice. The stop guard's emergency close works the same way.
  - **Reconcile:** an open `auto` journal trade whose coin has no position on the exchange (the entry did not
    fill, or sir closed it in Phantom before the fills were read) is marked closed silently.
- **`reset_peak()`** — called whenever REAL TRADE is switched on: `peak = null`, `flows_from = now`.

### `orion/trading/exchange.py`

- The part of `place()` after the approval (send with the take-profit and stop, then `_protect`) becomes
  `_open(info, client, address, plan, mid)`; `place()` keeps the dialog, the PriceMoved check and its behaviour.
  The market-close loop of `close()` becomes `_close(info, client, address, coins)`; `close()` keeps its dialog.
- **`auto_place(plan) -> str`** — refuses (TradingError) unless `settings.enabled()` and not `blocked`; reads
  the price again (moved more than `MOVE_LIMIT` since the plan → refused as stale); then `_open`.
- **`auto_close(coins, network) -> str`** — same guard; then `_close`.
- **`ensure_stop(coin, network, stop) -> str | None`** — the stop guard above; returns what to say, or None.
- **`transfers_since(network, since_ms) -> tuple[float, int]`** — the sum of `info.user_non_funding_ledger_updates`
  deltas that move USDC into or out of the perps account (deposit, withdraw incl. its fee, spot↔perp class
  transfer, sub-account / internal / spot transfers by direction) and the time of the last one. The exact delta
  types are checked against the live API with sir's address during implementation (read-only call).
- The module docstring's rule becomes: every open and close that a skill asks for (voice, chat) needs „Одобри“;
  only the autopilot calls `auto_place` / `auto_close`, they work only while REAL TRADE is on, and every order
  still passes `risk.plan`'s limits.

### Limits — `risk.Limits` and `settings.DEFAULTS["limits"]`

New field `max_drawdown_pct: float = 40.0`; the others stay (2 %, 10x, 6 %, 3). As today, the language model has
no skill that changes the limits.

### `orion/trading/modes.py`

`set_real(on, by_button=False)`: switching on without the button asks `confirm.ask("Автономна търговия · <РЕАЛНИ
ПАРИ | ТЕСТОВА МРЕЖА>", …, "Включи")`; refused → REAL TRADE stays off. Switching on calls `autopilot.reset_peak()`.
Switching off never asks. `HudApi.set_real_trading` (the window button, `app.py`) passes `by_button=True`; the
skills `set_real_trading` and `resume_trading` (reflex „включи реал трейд“, the model) do not.

### `orion/trading/watcher.py`

- `scan()`: with REAL TRADE on and a key connected → `autopilot.step(...)` and each line is announced; the old
  signal alert (`texts.signal_alert`) is used only while REAL TRADE is on without a key. Every signal still goes
  into the journal as before.
- `positions()`: with REAL TRADE on → `autopilot.guard(network)` lines are announced. The 48-hour reminder stays
  for trades sir opened himself through Orion (non-`auto` journal trades).
- Nothing autonomous runs while `exchange.blocked` (test mode's sandbox).

### Code Orion writes itself — `orion/self_improve.py`

Orion-written code may not import `orion.trading.exchange`, `orion.trading.autopilot`, `orion.trading.settings`
or `orion.trading.modes` (checked with the existing forbidden-module list, before the „Одобри и включи“ card). Its
skills therefore cannot place orders or switch REAL TRADE on.

### Journal — `orion/trading/journal.py`

`add_trade(plan, strategy, auto=False)` stores `"auto": true` for the autopilot's trades; `open_trade(coin)`
returns the open trade (its stop, time and `auto` flag) for the guard.

### Texts and docs (Trust Wallet → Phantom)

- `texts.CONNECT_STEPS`: the Phantom steps above (testnet: app.hyperliquid-testnet.xyz with Phantom).
  `texts.MAINNET_WARNING`: Orion trades by itself, the limits and the account stop.
- `modes.set_real` texts, skill docstrings (`connect_hyperliquid` — „където Phantom търгува Perps“,
  `resume_trading`, `set_real_trading`, `switch_trading_network`, the module docstring), `orion/trading/__init__.py`
  docstring, `web/src/components/KeyDialog.jsx`, `web/src/components/Console.jsx` tooltip, the README trading
  section, and the persona if it says real trades need approval.

## Error handling

- **The order went out but the result could not be read** → the existing `SENT_UNCHECKED` line; the autopilot
  still writes the journal trade, so the next `guard()` either finds the position and checks its stop, or
  reconciles the trade as not filled.
- **No connection / exchange errors** → retried on the next scan or check; told at most once per 6 hours.
- **The key expired** (Hyperliquid: „does not exist“) → the existing text „API ключът не е одобрен или е
  изтекъл — направете нов…“, once per 6 hours.
- **Orion is closed or the PC is off** → no new trades; the stops and targets in the exchange still work. On the
  next start `guard()` runs first-thing on the position check (time stop, stop guard, account stop).
- **Positions sir opens by hand in Phantom** are never touched; Hyperliquid has one position per coin, so Orion
  skips a coin sir already holds (`risk.plan` refuses), and sir's positions count towards the 3-position limit
  and today's loss.

## Testing

pytest with the fake Hyperliquid client already used by `tests/test_trading_exchange.py` (`exchange.client_factory`):

- a fresh signal of a checked strategy is opened with the signal's stop and target and 2 % risk; one of an
  unchecked strategy is not;
- the same signal is never traded twice; a connection error does not burn the signal; a stale signal is skipped
  with a journal line;
- daily loss limit, position limit and an existing position in the coin are respected;
- account stop: fires at −40 % from the high and switches REAL TRADE off; a withdrawal does not fire it; a
  deposit does not raise the high as profit; switching REAL TRADE on resets the high;
- stop guard: a missing stop is placed; a stop that cannot be placed closes the position;
- time stop closes only `auto` trades after 48 h; sir's trades still get the reminder;
- `auto_place` / `auto_close` refuse while REAL TRADE is off or the exchange is blocked;
- `set_real(True)` by voice asks and respects „Откажи“; by the button it does not ask; off never asks;
- self_improve rejects Orion-written code that imports the trading modules;
- the watcher calls the autopilot only with REAL TRADE on and a key; the old alert remains without a key.

Plus the existing suites (pytest, vitest, e2e) must still pass. **Live check, only when sir says:** the existing
smallest-order check (`testnet_check`) generalised to a network argument and run once on the real account: ≈11 $
BTC long, stop and target verified, closed at once (≈1 cent in fees).

## Out of scope

- SOL until a strategy passes the honest check for it; new strategies; machine learning.
- Moving money (deposits, withdrawals, spot↔perps) — sir does it in Phantom.
- Trading while Orion is closed; starting Orion with Windows.
- Managing positions sir opens by hand in Phantom.
- Phantom MCP server; Drift / Jupiter perps.
