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
