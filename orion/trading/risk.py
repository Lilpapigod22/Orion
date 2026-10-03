"""
Hard limits for every real trade — pure functions, no network. The exchange never gets an order that did
not pass plan(). Defaults (sir chose „агресивен“): ≤2 % of the account lost at the stop, leverage ≤10x,
≤6 % lost per day, ≤3 open positions. Isolated margin; the liquidation must be ≥1.5× further than the stop.
max_drawdown_pct is the autopilot's account stop: REAL TRADE switches itself off 40 % below the account's high.
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
    max_drawdown_pct: float = 40.0


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
