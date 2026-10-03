# Orion — crypto forecasts and trading on Hyperliquid (sub-project A)

Date: 2026-10-03 · Status: approved in conversation, awaiting review of this document

## Goal

Sir wants Orion to give the best possible forecasts for Bitcoin, Ethereum and Solana when he asks, and to
open long and short positions with real money. His wallet is Trust Wallet; its "Perps" tab trades on
Hyperliquid, so Orion trades on Hyperliquid through an API key that can trade but cannot withdraw.

Honesty is part of the goal. No method forecasts crypto "exactly". Orion's forecasts are probabilities
from rules whose results are measured on history Orion did not tune on and on live practice trades. Orion
always says how often a signal was right, and it says plainly when it currently has no edge. The language
model only explains numbers computed in code. It never decides a trade and never invents a figure (it has
done that before: the fake `sync_audio_video` skill).

Later sub-project (separate spec): B — a machine-learning forecast that is switched on only if it beats
these rules on data it never saw.

## Decisions (sir's choices)

| Question | Choice |
|---|---|
| Trading | Real money, every trade (open and close) only after sir presses „Одобри“ |
| Where | Hyperliquid (Trust Wallet Perps runs on it), API (agent) wallet: trade only, no withdrawals |
| Network | Testnet first; mainnet only after sir says so and confirms a warning dialog |
| Horizon | A few hours to 2 days: 1h entry candles, 4h and 1d trend filters, 48 h time stop |
| Risk limits | Aggressive: ≤2 % of the account lost per trade at the stop, leverage ≤10x, daily loss ≤6 %, ≤3 open positions |
| Signals | When sir asks, plus a background watch every 15 min that announces strong signals |
| Forecast method | A — rules + honest backtest now; B — machine learning later, only if it wins |
| Test mode | Practises mainly trading (virtual account, strategy lab, daily testnet order check) |

## What sir sees and says

- „Какво ще прави биткойнът?“ / „Прогноза за солана“ → a forecast for that coin. Example (numbers
  illustrative): *„Биткойн: 4-часовият тренд е нагоре. Сигнал ЛОНГ — отскок в тренда, сила 4 от 5. Вход около
  84 400, стоп 83 300 (−1,3 %), цел 86 600 (+2,6 %). В проверката: 64 сделки, печели 47 %, средно +0,3
  пъти риска на сделка след таксите. Финансирането е нормално. Това е вероятност, не гаранция.“*
  With no signal: the trend, the nearest levels and a 24 h range (≈68 % band from volatility, its hit rate
  measured) and „няма ясен сигнал — по-добре е да не се влиза“.
- „Сигнали“ / „Какво да търгувам?“ → all three coins in one answer.
- „Отвори лонг/шорт на биткойн“ → a trade proposal and the approval dialog (below).
- „Затвори етериума“ / „Затвори всичко“ → close with approval.
- „Какви позиции имам?“ / „Колко имам в сметката?“ → positions, live P/L, balance, today's P/L.
- „Колко позна тази седмица/месец?“ → the live forecast journal (real outcomes, not backtest).
- „Колко добри са стратегиите?“ → the backtest table per strategy and coin.
- „Свържи Hyperliquid“ → the key dialog. „Спри търговията“ / „Пусни търговията“ → kill switch.
  „Мини на истински пари“ / „Мини на тестовата мрежа“ → network switch (mainnet only via a warning dialog).
- The chart in the journal (existing `showChart`) gets entry, stop and target lines.
- A top-bar chip (next to the test and reels chips in `Jobs.jsx`) lists open positions with live P/L,
  e.g. `BTC LONG +1.2 % · ETH SHORT −0.4 %`, and shows `TESTNET` while on testnet.
- Background signals are spoken 08:00–23:00; at night they only go into the journal. Stop/target fills
  are announced („Етериум удари целта: +42 долара“).

## How it works

New package `orion/trading/`, one purpose per file:

### `data.py` — market data (no key)

Hyperliquid info API (`POST /info`): `candleSnapshot` (1h, 4h, 1d with volume — live signals),
`metaAndAssetCtxs` (mark/mid price, current funding, open interest, premium, size decimals, max leverage),
`fundingHistory` (paged, 500 per call, starts 2023-05-12). The API returns at most the latest 5000 candles
(≈7 months of 1h — measured 2026-10-03), too little for an honest out-of-sample test, so the **backtest
history** is Binance's public spot 1h klines (`data-api.binance.vision`, no key, `BTCUSDT`/`ETHUSDT`/
`SOLUSDT`) from 2023-05-12 (≈3.4 years), resampled to 4h and 1d, plus Hyperliquid's funding history. Fear & Greed
history from alternative.me (`fng/?limit=0`). The Binance history and the funding history are cached under
`memory/trading_cache/` and only the missing tail is fetched. Open interest has no history in the API: the watcher records snapshots, and
OI is used neither in rules nor in answers until enough
history exists.

### `signals.py` — indicators and the three strategies

Indicators (pure functions over candle lists; reuse `orion/markets.py` `ema/rsi/atr/levels` where they
fit): EMA 21/55 on 1h and 4h, EMA 50/200 on 1d, RSI(14), ATR(14), ADX(14), Donchian(20),
volume vs its 20-candle average, swing highs/lows, funding percentile over 90 days.

Strategies, evaluated on **closed** 1h candles, each mirrored for short:

1. **Trend pullback** — 4h trend up (EMA21 > EMA55, close > EMA55) and 1d not against (close > EMA200 or
   EMA50 > EMA200); 1h price pulls back into the EMA21–EMA55 zone and closes back above EMA21.
2. **Breakout** — 1h close above the Donchian-20 high with volume ≥ 1.5× average, ADX rising, 4h trend
   up or neutral.
3. **Extreme reversal** — funding in the top 5 % of the last 90 days and 4h RSI > 75, then a 1h close
   below the previous candle's low → short (mirror: bottom 5 %, RSI < 25, close above the previous high).

A `Signal` has: coin, strategy, side, entry (last close), stop (beyond the last swing or 1.5 × ATR,
whichever is further, capped at 3 × ATR), target (`reward` × the stop distance, default 2),
time stop 48 h, strength 1–5, the reasons as short Bulgarian phrases, and the strategy's backtest stats.
Strength = 1 + one point each for: 4h and 1d agree, volume above average, funding not crowded against the
trade, BTC 4h trend agrees (for BTC itself: Fear & Greed not extreme against the trade).

All strategy numbers (EMA lengths, thresholds, stop/target multiples) live in one parameter set per
strategy, loaded from `memory/trading_params.json` (defaults in code), so the lab can change numbers
without changing code.

### `backtest.py` — the honest check

- Replays every strategy candle by candle on the Binance history for each coin, with the same `Signal`
  code (no separate backtest logic). Entry at the next candle's open.
- Costs: taker fee on entry and exit (default 0.045 %, read from `userFees` once connected), slippage
  (BTC 0.02 %, ETH 0.03 %, SOL 0.05 %), hourly funding from `fundingHistory`. If stop and target are both
  inside one candle, the stop counts. Time stop exits at the close after 48 h.
- Parameters are tuned only on the first 70 % of the history (a small grid, ≤24 variants per strategy);
  every reported number comes from the last 30 % (out-of-sample).
- Reported per strategy × coin: trades, win rate with a 95 % Wilson interval, average result in R
  (multiples of the risk), profit factor, max drawdown in R, expectancy after costs.
- **A strategy is enabled for a coin only if, out-of-sample: ≥30 trades, expectancy > 0 after costs,
  profit factor ≥ 1.1.** Otherwise Orion says the strategy currently does not work for that coin. If none
  passes anywhere, Orion says it has no edge right now.
- The 24 h range forecast is checked the same way (share of days the price stayed inside the band).
- Results go to `memory/trading_stats.json`; the backtest re-runs weekly (background, in a thread) and
  on demand.

### `journal.py` — live track record

Every signal Orion gives (asked, watched or practised) and every trade is appended to
`memory/trading_journal.json` with its outcome, resolved later from Hyperliquid's 1h candles (so outcomes
are correct even if the PC was off). This answers „колко позна“ and feeds the strategy lab.

### `risk.py` — hard limits (pure functions, no I/O)

Limits from `trading_settings.json` (defaults: risk 2 %, leverage 10x, daily loss 6 %, positions 3).
- Size = (equity × risk %) / |entry − stop|, rounded down to the coin's size decimals; refuse below
  Hyperliquid's $10 minimum.
- Leverage = the smallest integer with margin (notional / leverage) ≤ equity / max positions. If that
  needs more than the max leverage, the size is reduced to fit and Orion says the risk is lower than 2 %.
- Isolated margin. Estimated liquidation distance ≈ 1/leverage − maintenance margin (half the initial
  margin at the coin's max leverage); **it must be ≥ 1.5 × the stop distance**, else lower leverage, else
  refuse.
- Daily loss (Europe/Sofia day): realised P/L + fees + funding today, plus this trade's risk, must stay
  within the limit; reaching it locks new trades until midnight.
- Open positions ≤ max; one position per coin (Hyperliquid nets per coin).
- Each refusal returns a Bulgarian reason Orion says out loud.

### `exchange.py` — orders (the only file that talks to the exchange with a key)

Uses the official `hyperliquid-python-sdk` (`Info`, `Exchange`) with the agent key.
- **Approval is enforced here**, in `place()` and `close()`, via `orion.confirm.ask` — not in the skill.
  So no skill, including code Orion writes itself, can trade without sir's click. The dialog shows coin,
  side, size (coins and $), leverage, entry, stop (loss in $ and %), target (profit in $), estimated
  liquidation, fees, network (TESTNET/РЕАЛНИ ПАРИ in the title).
- After approval: re-read the mid price; if it moved > 0.3 % from the proposal, cancel and re-propose
  with fresh numbers.
- Order: set isolated leverage, then entry (IOC limit, 0.5 % slippage cap) with take-profit and stop-loss
  trigger orders (reduce-only, market) in one `normalTpsl` group. Then verify the position and both
  trigger orders exist. A missing stop is placed again once; **if it is still missing, the position is
  closed at market at once.** A position never stays without a stop.
- Stops are never moved further away. Moving a stop to entry (break-even) is a proposal with approval.
- Network: the testnet URL is a constant; mainnet needs `network = "mainnet"` in settings, set only by
  the switch skill after a warning dialog. While test mode's sandbox is active, the mainnet client
  refuses every call.
- The only path without approval is `testnet_check()` for test mode's daily order check: it builds its
  own client with the hard-wired testnet URL and the testnet key, places the minimum size only, and
  cannot be pointed at mainnet.
- Errors (expired key, insufficient margin, rejected order) become short Bulgarian messages.
- Fills: while positions are open, a 1-minute poll of `userFills` announces stop/target/time-stop exits
  and updates the top-bar chip. The 48 h time stop is announced („времето ѝ изтече“); sir closes the trade
  with one command and its approval dialog — a dialog the watch opened by itself could collide with another
  approval.

### `settings.py` — `trading_settings.json` (git-ignored, this PC only)

Network, master address, agent key(s) (mainnet and testnet separately) encrypted with Windows DPAPI
(`CryptProtectData` via ctypes, user scope), limits, trading enabled flag, voice hours. The language model
has no tool that changes limits; sir edits them in the file or a settings screen later.

### `watcher.py` — background watch

Own thread started in `app.py` (pattern of `_reminder_loop`, respects `self_test.sandbox_lock`). Every
15 min: refresh data, evaluate signals (new ones appear at most once per closed hour), log them to the
journal, record an OI snapshot, and announce a signal when strength ≥ 4, the strategy is enabled for that
coin, and the same coin/side was not announced in the last 6 h. Voice only 08:00–23:00. While positions
are open it also runs the 1-minute fill poll.

### `practice.py` and the strategy lab — test mode practises trading

Test mode (`orion/self_test.py`) gets a trading stage that runs **every round**; the existing skill and
understanding stages run every 3rd round.
1. **Practice account** (`memory/trading_practice.json`, $10 000 virtual): in test mode Orion opens every
   signal of every strategy without asking, with the same sizing and leverage rules (`risk.size_for`) and
   the backtest's cost model, on live mainnet prices. The position-count limit is not applied, so every
   signal is measured. Outcomes resolve from candles (also after the PC was off).
2. **Strategy lab**: tries parameter variants on the tuning part of history. A variant replaces the
   current parameters only if (a) it beats them out-of-sample by ≥10 % expectancy and passes the enable
   rule, and then (b) it beats them over its first 20 practice trades, which run alongside as a shadow.
   Promotions write `memory/trading_params.json` and keep the previous sets for rollback. Only numbers
   change; new code still needs „Одобри и включи“.
3. **Testnet order check**, once a day, only if a testnet key is set: open the minimum size, verify the
   stop and target exist, close, report.
4. **Understanding asks** for the new commands are added to `self_test_cases.py` (actions stubbed).
„Как мина теста“ also reports: practice balance and P/L, trades and win rate per strategy, lab
promotions, the testnet check.

### Skills, reflexes, router, prompt

- `skills/crypto_trading_skills.py`: `crypto_forecast(coin)`, `crypto_signals()`, `open_trade(coin,
  side)`, `close_trade(coin)` (`"всички"` closes all), `trading_positions()`, `trading_account()`,
  `forecast_record(period)`, `strategy_report()`, `connect_hyperliquid()`, `pause_trading()`,
  `resume_trading()`, `switch_trading_network(network)`. Forecast texts end with the existing
  "not investment advice" note.
- Reflexes (deterministic, before the model, because the model is unreliable with actions): open
  long/short, close, close all, stop/resume trading, positions. Coin names reuse `markets.ALIASES`
  (BTC/ETH/SOL only; other coins → „засега търгувам само биткойн, етериум и солана“).
- `orion/router.py`: a new keyword group (лонг, шорт, позиция, сделка, трейд, ливъридж, стоп, хиперликуид,
  прогноза, сигнал…). `brain.INTENT_TOOLS`: forecast questions force `crypto_forecast`.
- `config.py` persona line: forecasts come only from `crypto_forecast`; say the win rate and that it is a
  probability.

### Window (web/, React)

- `bridge.js`: `hud.setTrading({network, positions: [{coin, side, pnl_pct, pnl_usd}]})` → store →
  a `trading` chip in `Jobs.jsx`.
- `showChart` payload gains optional `entry`, `stop`, `target` lines.
- The approval dialog is the existing `showConfirm`.

## Errors and safety

- No connection to Hyperliquid → forecasts say data is unavailable; no stale numbers are presented as
  live (cache age is stated if older than 2 h).
- Seed phrases are never asked for or accepted; the key dialog accepts only an agent private key and the
  master address, and says so.
- The agent key cannot withdraw. Even if the PC is compromised, the funds cannot be moved out by Orion's
  key; the key can be revoked on app.hyperliquid.xyz/API.
- Approval at the lowest level; test-mode sandbox rejects every confirmation and blocks mainnet; practice
  trades never touch the exchange; the testnet URL is hard-wired for the daily check.
- A position without a stop is closed immediately. Stops never move away. Daily loss lock. Kill switch.
- `trading_settings.json`, `memory/trading_*` are git-ignored (memory/ already is; add the settings file).

## Dependencies

`hyperliquid-python-sdk` (pulls `eth-account`, `msgpack`, `websocket-client`; a few MB). Check free space
on C: first (see the disk-space memory).

## Testing

- pytest, no network: `risk.py` (sizing, rounding, minimum order, leverage fitting, liquidation rule,
  daily lock, position limit); indicators and each strategy on fixed candle fixtures (signal and no-signal
  cases, long and short); backtest on synthetic series with known outcomes (stop-before-target rule, fees,
  funding, time stop, 70/30 split, enable rule); journal outcome resolution; DPAPI round-trip.
- `exchange.py` against a fake SDK: no order without approval; rejection does nothing; price moved >0.3 %
  → re-proposal; missing stop → re-placed, then position closed; mainnet refused in sandbox; error texts.
- Test mode: practice trades and lab promotion on recorded candles; sandbox leaves real files untouched.
- **No automated test ever sends a real order.** Final manual check on testnet: connect, open, see the
  stop and target on app.hyperliquid-testnet.xyz, close, hear the announcements.

## Acceptance criteria

1. Asking for a BTC/ETH/SOL forecast gives direction (or "no signal"), entry, stop, target, strength and
   the strategy's out-of-sample stats, all computed in code, in under ~15 s with a warm cache.
2. `strategy_report` shows the per-strategy, per-coin table; disabled strategies are named as such.
3. On testnet, „отвори лонг на биткойн“ shows the dialog with correct numbers; after approval the
   position, stop and target exist on the exchange; rejection does nothing.
4. Every limit refuses with a spoken reason; the daily loss lock and the kill switch work.
5. Background watch announces strong signals once, by day only, and fills are announced.
6. Test mode runs the trading stage every round, keeps a practice account, reports it, and can promote a
   parameter set only through both gates.
7. Mainnet trading is possible only after the switch dialog; sir's approval is required for every open
   and close on both networks. The only exceptions are virtual practice trades and the daily
   minimum-size `testnet_check()` in test mode.
