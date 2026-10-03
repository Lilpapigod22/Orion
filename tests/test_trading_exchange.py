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


def test_a_lost_connection_after_sending_says_to_check_the_positions(fake, approve):
    info, ex = fake
    approve(True)
    send = ex.bulk_orders

    def send_then_drop(orders, grouping="na"):
        result = send(orders, grouping)

        def down(address):
            raise OSError("connection reset")
        info.user_state = down
        return result

    ex.bulk_orders = send_then_drop
    with pytest.raises(exchange.TradingError, match="изпратена"):
        exchange.place(plan())
    assert "BTC" in exchange.last_open


def test_a_lost_connection_while_checking_the_stop_says_so_too(fake, approve):
    info, ex = fake
    approve(True)

    def down(address):
        raise OSError("connection reset")
    info.frontend_open_orders = down
    with pytest.raises(exchange.TradingError, match="изпратена"):
        exchange.place(plan())
    assert "BTC" in exchange.last_open


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
