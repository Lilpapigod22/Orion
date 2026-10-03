"""
The only place that talks to Hyperliquid with a key (Phantom's Perps tab is this Hyperliquid account).
Every open and close a skill asks for (voice, chat) passes through confirm.ask (sir's „Одобри“) HERE.
Only the autopilot calls auto_place / auto_close: they work only while REAL TRADE is on, and every order
they send was made by risk.plan within the hard limits. Code Orion writes itself may not import this
module (self_improve). The agent (API) key can trade but cannot withdraw.

After approval the price is read again (moved > 0.3 % -> PriceMoved, the skill proposes again), isolated
leverage is set, and the entry goes in one group with the take-profit and the stop-loss. A position is
never left without a stop: if the stop cannot be placed, the position is closed at once.
"""
import math
import threading
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
TIMEOUT = 15                # seconds per Hyperliquid request — a stalled request must not freeze the watch
REAL_TRADE_OFF = "REAL TRADE е спрян — автопилотът не търгува."
_open_lock = threading.Lock()   # one open at a time: a voice trade and the autopilot never stack on one coin
PRICE_MOVED = "Цената се помести, докато смятах сделката — пропускам я."
SENT_UNCHECKED = ("Поръчката е изпратена, но връзката с борсата прекъсна преди проверката на стопа. Кажете "
                  "„какви позиции имам“ — ако позицията е там без стоп, затворете я с „затвори …“.")


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
        raise TradingError("Hyperliquid не е свързан. За истински пари кажете „свържи Hyperliquid“ и включете REAL "
                           "TRADE. Мога да търгувам на демо сметка — кажете „направи демо сметка с 1000 долара“.")
    address, key = found
    url = constants.MAINNET_API_URL if network == "mainnet" else constants.TESTNET_API_URL
    client = Exchange(eth_account.Account.from_key(key), url, account_address=address, timeout=TIMEOUT)
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
    try:
        return _position(info, address, plan.coin)
    except Exception as e:  # the order is out, but we cannot see the result — never say "nothing happened"
        last_open.add(plan.coin)
        raise TradingError(SENT_UNCHECKED) from e


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


def _open(info, client, address: str, plan: risk.OrderPlan, mid: float) -> str:
    """Sends the entry with its target and stop and makes sure the stop exists. Returns what Orion says. The
    positions are read again first, under _open_lock: a voice trade approved after the autopilot opened the same
    coin (or the other way round) is refused, never stacked on it."""
    with _open_lock:
        open_now = {item["position"]["coin"] for item in info.user_state(address).get("assetPositions", [])
                    if float(item["position"]["szi"])}
        if plan.coin in open_now:
            raise TradingError(f"Междувременно се отвори позиция в {NAMES[plan.coin]} — не добавям към нея.")
        if len(open_now) >= settings.limits().max_positions:
            raise TradingError("Междувременно се стигна лимитът на отворените позиции — сделката не е отворена.")
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
        raise TradingError(REAL_TRADE_OFF)
    return _client(network)


def auto_place(plan: risk.OrderPlan) -> str:
    """The autopilot's open — no dialog: only while REAL TRADE is on. Returns what Orion says."""
    info, client, address = _autopilot_client(plan.network)
    mid = float(info.all_mids()[plan.coin])
    if abs(mid / plan.entry - 1) > MOVE_LIMIT:
        raise TradingError(PRICE_MOVED)
    return _open(info, client, address, plan, mid)


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
    """Test mode's daily check — always the testnet, even while the sandbox blocks everything else."""
    return smallest_check("testnet")


def smallest_check(network: str) -> str:
    """The smallest BTC long (≈11 $), its stop and target verified, then closed at once. The testnet daily
    (testnet_check); the real account once, on sir's word, before the autopilot's first real trade."""
    info, client, address = client_factory(network)
    where = "в тестовата мрежа" if network == "testnet" else "в истинската сметка"
    if _position(info, address, "BTC"):
        return f"Проверката {where} е пропусната — там вече има позиция в биткойн."
    decimals = next(int(u["szDecimals"]) for u in info.meta()["universe"] if u["name"] == "BTC")
    mid = float(info.all_mids()["BTC"])
    size = math.ceil(11 / mid * 10 ** decimals) / 10 ** decimals
    plan = risk.OrderPlan("BTC", "long", size, mid, risk.round_price(mid * 0.98, decimals),
                          risk.round_price(mid * 1.02, decimals), 1, size * mid, size * mid, 0.0, 0.0, 0.0, 0.0,
                          network, sz_decimals=decimals)
    ok = False
    try:
        position = _send(info, client, address, plan, mid)
        if not position:
            return f"Проверката {where}: входът не се изпълни."
        stops, targets = _protection(info, address, "BTC", "long", position["entry"])
        ok = bool(stops) and bool(targets)
    finally:
        if _position(info, address, "BTC"):
            client.market_close("BTC", slippage=CLOSE_SLIPPAGE)
        for order in info.frontend_open_orders(address):
            if order.get("coin") == "BTC" and order.get("reduceOnly"):
                client.cancel("BTC", order["oid"])
    if ok:
        return f"Проверката {where} мина: входът, стопът и целта се поставиха и позицията се затвори."
    return f"Проверката {where} НЕ мина: стопът или целта липсваха. Позицията е затворена."
