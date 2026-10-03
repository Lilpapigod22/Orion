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
        self.answer = None     # auto_place answers this without placing

    def account_state(self, network):
        if self.down:
            raise OSError("connection reset")
        coins = {coin: {"mid": mid, "sz_decimals": 3, "max_leverage": 20} for coin, mid in self.mids.items()}
        return risk.AccountState(self.equity, dict(self.positions), self.lost), coins

    def auto_place(self, plan):
        if self.fail:
            raise self.fail
        if self.answer:
            return self.answer
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
    assert guard(ex) == []                             # the high rises one check later
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
    assert guard(ex) == []
    ex.flows = (0.0, 0)
    assert guard(ex) == []
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
    ex.positions = {"BTC": {"side": "long"}, "ETH": {"side": "long"}}
    ex.stop_said = "Позицията в биткойн беше без стоп — поставих го на 98.00."
    assert guard(ex) == [(ex.stop_said, True)]
    assert ex.checked == [("BTC", 98.0)]


def test_the_time_stop_closes_only_the_autopilots_trades_after_48_hours(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    journal.add_trade(plan_for("ETH", stop=1900.0), "без сигнал")
    ex.positions = {"BTC": {"side": "long"}, "ETH": {"side": "long"}}
    ex.clock["now"] += 47 * data.HOUR
    assert guard(ex) == [] and ex.closed == []
    ex.clock["now"] += 1 * data.HOUR
    assert guard(ex) == [(texts.auto_time_stop("BTC", "long"), True)]
    assert ex.closed == ["BTC"]


def test_a_time_stop_that_fails_is_retried_but_said_once(ex, monkeypatch):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    ex.positions = {"BTC": {"side": "long"}}
    tries = []
    monkeypatch.setattr(exchange, "auto_close", lambda coins, network: tries.append(coins) or "Няма какво да затварям.")
    ex.clock["now"] += 49 * data.HOUR
    assert len(guard(ex)) == 1 and guard(ex) == []
    assert tries == [["BTC"], ["BTC"]]


def test_no_time_stop_after_real_trade_went_off(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    ex.positions = {"BTC": {"side": "long"}}
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
def test_another_network_starts_its_own_high(ex):
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


# --- Fix round 1 ----------------------------------------------------------------------------------
def test_a_withdrawal_seen_in_the_ledger_before_the_balance_does_not_fire(ex):
    autopilot.reset_peak()
    guard(ex)
    ex.flows = (-500.0, T0 + 5)                        # the balance still shows the money
    assert guard(ex) == []
    ex.flows, ex.equity = (0.0, 0), 500.0
    assert guard(ex) == [] and guard(ex) == []
    assert settings.enabled() and autopilot.load()["peak"] == 500.0


def test_a_deposit_seen_in_the_balance_before_the_ledger_is_not_counted_twice(ex):
    autopilot.reset_peak()
    guard(ex)
    ex.equity = 2000.0                                 # the ledger does not show the deposit yet
    guard(ex)
    ex.flows = (1000.0, T0 + 5)
    guard(ex)
    assert autopilot.load()["peak"] == 2000.0
    ex.flows, ex.equity = (0.0, 0), 1250.0             # floor 1200
    assert guard(ex) == [] and guard(ex) == [] and settings.enabled()


def test_the_guard_leaves_the_other_networks_trades_alone(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)          # a mainnet trade
    assert autopilot.guard("testnet", risk.AccountState(1000.0)) == []
    assert [t["coin"] for t in journal.open_trades()] == ["BTC"] and ex.checked == []


def test_a_stale_trade_is_closed_before_a_new_one_in_the_same_coin(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)          # closed while Orion was off
    ex.clock["now"] += 47 * data.HOUR
    ex.found["BTC"] = [sig(time=2)]
    step(ex)
    assert [t["time"] for t in journal.open_trades()] == [ex.clock["now"]]
    ex.clock["now"] += 1 * data.HOUR
    assert guard(ex) == [] and ex.closed == []


def test_a_position_on_the_other_side_is_never_touched(ex):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)          # long in the journal
    ex.positions = {"BTC": {"side": "short"}}                          # sir's own short in Phantom
    ex.clock["now"] += 49 * data.HOUR
    assert guard(ex) == [] and ex.checked == [] and ex.closed == []
    assert journal.open_trades() == []


def test_one_failing_trade_does_not_stop_the_guard_of_the_others(ex, monkeypatch, capsys):
    journal.add_trade(plan_for("BTC"), "breakout", auto=True)
    journal.add_trade(plan_for("ETH", stop=1900.0), "breakout", auto=True)
    ex.positions = {"BTC": {"side": "long"}, "ETH": {"side": "long"}}
    checked = []

    def ensure(coin, network, stop):
        checked.append(coin)
        if coin == "BTC":
            raise OSError("connection reset")
    monkeypatch.setattr(exchange, "ensure_stop", ensure)
    assert guard(ex) == [(texts.AUTO_NO_CONNECTION, True)]
    assert checked == ["BTC", "ETH"] and "[Autopilot] OSError: connection reset" in capsys.readouterr().out


def test_a_price_that_moved_is_a_journal_only_skip(ex):
    ex.fail = exchange.TradingError(exchange.PRICE_MOVED)
    ex.found["BTC"] = [sig()]
    assert step(ex) == [(texts.auto_skipped(sig(), exchange.PRICE_MOVED), False)]


def test_an_order_that_did_not_fill_is_a_journal_only_skip(ex):
    ex.answer = "Входът не се изпълни — цената избяга. Нищо не е отворено."
    ex.found["BTC"] = [sig()]
    assert step(ex) == [(texts.auto_skipped(sig(), ex.answer), False)]
    assert journal.open_trades() == []


def test_a_failed_journal_write_after_an_order_still_tells_the_trade(ex, monkeypatch, capsys):
    def full_disk(*args, **kwargs):
        raise OSError("No space left on device")
    monkeypatch.setattr(journal, "add_trade", full_disk)
    ex.found["BTC"] = [sig()]
    assert step(ex) == [(texts.auto_opened(ex.placed[0], "breakout"), True)]
    assert autopilot.load()["traded"] == [["BTC", "breakout", "long", 1]]
    assert "[Autopilot] OSError: No space left on device" in capsys.readouterr().out


def test_a_failed_state_write_still_returns_the_lines(ex, monkeypatch):
    def full_disk(state):
        raise OSError("No space left on device")
    monkeypatch.setattr(autopilot, "save", full_disk)
    ex.found["BTC"] = [sig()]
    assert step(ex)[0][1] is True
    assert guard(ex) == []


def test_real_trade_switched_off_mid_scan_is_journal_only(ex):
    ex.fail = exchange.TradingError(exchange.REAL_TRADE_OFF)
    ex.found["BTC"] = [sig()]
    assert step(ex) == [(texts.auto_skipped(sig(), exchange.REAL_TRADE_OFF), False)]
