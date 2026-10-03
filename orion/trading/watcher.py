"""
The background watch (own thread, started by app.py). Every 15 minutes it checks the three coins: each
new signal goes into the journal, and a strong one (strength ≥ 4, from a strategy that passed the honest
check) is announced — by voice 08:00–23:00, otherwise only in the journal. With a key connected it checks
the account (every minute while positions are open, else every 5): the top-bar chip, closed trades, and
the 48-hour time stop (announced; sir closes it with one command and the approval dialog). It holds test
mode's sandbox lock while it works, so it never touches the sandbox's temporary files.
"""
import time
from datetime import datetime

from . import COINS, NAMES, backtest, data, exchange, journal, market, settings, signals, texts

SCAN_EVERY = 15 * 60
RESOLVE_EVERY = 60 * 60
REFRESH_RETRY = 30 * 60
REPEAT_HOURS = 6


class Watcher:
    def __init__(self, say, hud, lock, clock=time.time):
        self.say, self.hud, self.lock, self.clock = say, hud, lock, clock
        self.last_scan = self.last_positions = self.last_resolve = self.last_refresh = -1e18
        self.announced: dict[tuple[str, str], float] = {}
        self.fills_from = int(clock() * 1000)
        self.time_stop_told: set[str] = set()

    def run(self) -> None:
        while True:
            self.tick()
            time.sleep(5)

    def _safe(self, job) -> None:
        try:
            job()
        except Exception as e:  # noqa: BLE001 — the watch must never stop Orion
            print(f"[Trading] {getattr(job, '__name__', 'job')}: {type(e).__name__}: {e}")

    def tick(self) -> None:
        now = self.clock()
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
        if now - self.last_refresh >= REFRESH_RETRY and backtest.stale():
            self.last_refresh = now
            backtest.refresh_async(self.lock)

    # --- Signals ---------------------------------------------------------------------------------
    def scan(self) -> None:
        report = backtest.load()
        strength = settings.load()["announce_strength"]
        for coin in COINS:
            for s in signals.latest(market.live(coin)):
                if journal.add_signal(s, "watch") and self._worth(s, report, strength):
                    self.announce(texts.signal_alert(s, report))
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

    # --- The account ------------------------------------------------------------------------------
    def positions(self) -> None:
        network = settings.network()
        if not settings.account(network):
            self.hud("setTrading", None)
            return
        state, _ = exchange.account_state(network)
        self.hud("setTrading", {"network": network, "positions": [
            {"coin": coin, "side": p["side"], "pnl_usd": round(p["pnl"], 2),
             "pnl_pct": round(p["pnl"] / p["value"] * 100, 2) if p["value"] else 0.0}
            for coin, p in state.positions.items()]})
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
