# Orion — demo accounts, history simulation and three mode buttons (sub-project A2)

Date: 2026-10-03 · Status: approved in conversation (sir: „да“ to both sections and to writing the plan and
the code right after). Builds on `2026-10-03-crypto-trading-design.md`.

## Why

Sir asked Orion „искам да тренираш сметка която е с 1000 долара…“ and Orion answered that it cannot manage
any account, not even a simulated one — true: the practice account only existed inside test mode and no
skill could reach it; without a Hyperliquid key every trading skill said „не е свързан“. Sir wants:
virtual demo accounts Orion trades **by itself**, tests and simulations, real trading as before, and three
buttons that make the modes visible.

## Decisions (sir's choices)

| Question | Choice |
|---|---|
| Real money | With approval, as before: Orion finds and proposes, every open/close needs „Одобри“. Only demo trades without asking. |
| Demo accounts | Several at once, with names, each with its own risk |
| Buttons | Three: TEST MODE (skills/understanding only, as before trading was added), DEMO TEST (Orion trades the demo accounts by itself; also the strategy lab and the daily testnet check), REAL TRADE (real Hyperliquid account: forecasts and advice when asked, trades only with approval; off = no real orders) |
| Real signal alerts | Kept while REAL TRADE is on (sir's first choice); sir can ask to turn them off later |

## What sir sees and says

- „Направи демо сметка с 1000 долара“ → account „демо 1“ (then „демо 2“…), risk 2 %, checked strategies
  only. „Направи демо сметка „предпазлива“ с 500 долара и 1 % риск“ → a named account with its own risk.
  „…с всички сигнали“ → the account also trades strategies that did not pass the honest check.
  Amounts in лева are converted to dollars at today's rate (demo accounts are in dollars, like the exchange).
  The first time DEMO TEST is switched on without any account, „демо 1“ with 1000 $ is created and announced.
- While DEMO TEST is on, every demo account trades the same signals by itself on live Hyperliquid prices;
  the journal shows „DEMO демо 1: отворих лонг на биткойн…“ / „…затворих: +12.40 $“ — no voice.
- „Как върви демото?“ / „Как вървят демо сметките?“ → per account: balance, change in %, closed trades,
  wins, open positions. The top-bar chip shows `DEMO · демо 1 +3.2% · предпазлива −0.4%`.
- „Изтрий демо сметката „предпазлива““, „Започни демото отначало“ (same start and risk, trades cleared),
  „Избери демо сметката „предпазлива““ (the one manual commands use).
- „Отвори лонг на биткойн“ / „Затвори биткойна“: to the active demo account (instantly, no dialog) when
  only DEMO TEST is on or when sir says „в демото“; to the real account with the approval dialog when
  REAL TRADE is on; with both off Orion says which button to switch on.
- „Симулирай 1000 долара за последната година“ (also „за 6 месеца“, „за 90 дни“, „с 1 % риск“, „с всички
  сигнали“) → the strategies replayed on history across the three coins with compounding: final balance,
  return %, max drawdown %, trades and wins, best and worst month, and the line „Миналото не гарантира
  бъдещето.“
- Without a key Orion no longer says „не мога“: „За истински пари кажете „свържи Hyperliquid“ и включете
  REAL TRADE. Мога да търгувам на демо сметка — кажете „направи демо сметка с 1000 долара“.“
- Buttons by voice: „включи/спри демо теста“, „включи/спри реал трейд“; the old „спри/пусни търговията“
  now move the REAL TRADE button.

## How it works

- `orion/trading/demo.py` — the virtual exchange: `memory/trading_demo.json` = `{"accounts": {name: account},
  "active": name}`; an account is `{start, balance, risk_pct, all_signals, created, open: [], closed: []}`.
  One engine for demo and practice: `open_signals` (one position per coin for demo accounts; per coin +
  strategy + variant for the practice account), `settle` (the backtest's `exit_walk`, costs and funding),
  `open_manual` / `close_manual`, `by_strategy`, `step` (settle + open the latest signals for every account,
  filtered by `backtest.is_enabled` unless `all_signals`), `equity`. Sizing: risk % of the current balance
  over the stop distance, capped by the leverage limit.
- `orion/trading/practice.py` keeps the practice account and the daily testnet check but uses the demo
  engine; `practice.step(prepared_by_coin)` replaces `practice.run`.
- `orion/trading/lab.py` is split so the minutes of CPU in `search` run **without** test mode's sandbox lock
  (reminders and price alerts take that lock too): `judge` (gate b, file) → `due` (which strategy) →
  `search` (CPU, reads only the candle cache) → `start` (gate a result, file).
- `orion/trading/simulate.py` — `run(balance, days, risk_pct, all_signals)`: per coin, the allowed strategies'
  `backtest.simulate` trades in the window, merged in time, one position per coin, risk sized on the
  realised balance at entry, equity curve → drawdown, monthly returns.
- `orion/trading/modes.py` — `set_demo(on)`, `set_real(on)`: settings + `trading.on_switch(name, on)`
  (app.py moves the window's button) + the sentence Orion says. `settings`: `demo` (default off) and
  `enabled` = REAL TRADE (default changes to **off**).
- `watcher.py`: one market fetch per scan feeds the journal, the real alerts (only with REAL TRADE on), the
  demo step and the practice step (only with DEMO TEST on); lab search outside the lock; the chip payload
  becomes `{network, positions, demo: [{name, pct}]}` and is sent even without a key.
- Test mode (`self_test.py`) goes back to skills + understanding every round (no trading stage).
- Skills: `create_demo_account(balance, name="", currency="USD", risk_pct=2, all_signals=False)`,
  `demo_status()`, `delete_demo_account(name)`, `reset_demo_account(name="")`, `choose_demo_account(name)`,
  `simulate_history(balance, days=365, currency="USD", risk_pct=2, all_signals=False)`,
  `set_demo_test(on)`, `set_real_trading(on)`; `open_trade(coin, side, account="")` and
  `close_trade(coin, account="")` route as above; `pause_trading`/`resume_trading` call `modes.set_real`.
- Reflexes for the common phrases (create, status, delete, reset, choose, simulate, the buttons); router
  words; an intent nudge for „демо/симулац/тренировъчна сметка“; persona lines (never „cannot trade“).
- Window: switches `demo` („Demo test“) and `real` („Real trade“) next to the three existing ones;
  `pywebview.api.set_demo_mode` / `set_real_trading`; start-up returns `demoMode` / `realTrading`.

## Safety

- Demo trades never touch the exchange; real orders still pass `exchange.place/close` with approval.
- REAL TRADE off blocks real opens (as „спри търговията“ did); closing a real position stays possible.
- Demo accounts and the simulation report the same costs as the backtest; the simulation states that the
  past does not guarantee the future.

## Testing

pytest for the demo engine, practice on the engine, the lab split (search runs with the lock free), the
simulation (compounding, one position per coin, drawdown, months, no allowed strategy), modes and routing,
the skills, the watcher (demo only with DEMO TEST on, real alerts only with REAL TRADE on, chip without a
key), test mode without trading, the reflexes; Vitest for the two switches, their API calls and the demo
chip; e2e and a screenshot of the console with five switches.
