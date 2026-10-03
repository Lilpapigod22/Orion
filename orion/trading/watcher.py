"""
The background watch (own thread, started by app.py). Every 15 minutes it fetches the three coins once and
uses them for everything: each new signal goes into the journal; with REAL TRADE on and a key connected, the
autopilot trades the checked strategies by itself (autopilot.step — voice 08:00–23:00, journal always);
REAL TRADE on without a key announces a strong signal of a checked strategy instead; with DEMO TEST on, the
demo accounts and the practice account trade by themselves (journal only). With a key connected it checks
the real account (every minute while positions are open, else every 5): closed trades, the autopilot's
guard (account stop, stops, its 48-hour time stop) and the 48-hour reminder for sir's own trades. The
top-bar chip shows the real positions and the demo accounts. It holds test mode's sandbox lock while it touches
files; the lab's minutes of CPU and the testnet order check run without it.
"""
import time
from datetime import datetime

from . import (COINS, NAMES, autopilot, backtest, data, demo, exchange, journal, lab, market, practice, settings,
               signals, texts)

SCAN_EVERY = 15 * 60
RESOLVE_EVERY = 60 * 60
REFRESH_RETRY = 30 * 60
LAB_EVERY = 60 * 60
REPEAT_HOURS = 6


class Watcher:
    def __init__(self, say, hud, lock, clock=time.time):
        self.say, self.hud, self.lock, self.clock = say, hud, lock, clock
        self.last_scan = self.last_positions = self.last_resolve = self.last_refresh = self.last_lab = -1e18
        self.announced: dict[tuple[str, str], float] = {}
        # from launch: older fills are never replayed — they would close journal trades of coins that are open again
        self.fills_from = int(clock() * 1000)
        self.time_stop_told: set[str] = set()

    def run(self) -> None:
        while True:
            self.tick()
            time.sleep(5)

    def _safe(self, job, *args):
        try:
            return job(*args)
        except Exception as e:  # noqa: BLE001 — the watch must never stop Orion
            print(f"[Trading] {getattr(job, '__name__', 'job')}: {type(e).__name__}: {e}")
            return None

    def tick(self) -> None:
        now = self.clock()
        strategy, testnet = None, False
        with self.lock:
            if now - self.last_positions >= (60 if exchange.last_open else 300):
                self.last_positions = now   # first: the guard (account stop, stops) before any new trade
                self._safe(self.positions)
            if now - self.last_scan >= SCAN_EVERY:
                self.last_scan = now
                self._safe(self.scan)
            if now - self.last_resolve >= RESOLVE_EVERY:
                self.last_resolve = now
                self._safe(journal.resolve)
            if now - self.last_lab >= LAB_EVERY and self._safe(settings.demo_on):
                self.last_lab = now
                strategy = self._safe(lab.due)
                if self._safe(practice.testnet_due):
                    self._safe(practice.mark_testnet)
                    testnet = True
        if strategy:
            self._safe(self.lab_search, strategy)
        if testnet:
            self._safe(self.testnet)
        if now - self.last_refresh >= REFRESH_RETRY and backtest.stale():
            self.last_refresh = now
            backtest.refresh_async(self.lock)

    # --- Signals, real alerts, demo trades --------------------------------------------------------
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
        if options["demo"]:
            self.demo_step(prepared, report)
        data.record_open_interest(data.assets())

    def _worth(self, s, report, strength: int) -> bool:
        if s.strength < strength or not backtest.is_enabled(report, s.coin, s.strategy):
            return False
        key = (s.coin, s.side)
        if self.clock() - self.announced.get(key, -1e18) < REPEAT_HOURS * 3600:
            return False
        self.announced[key] = self.clock()
        return True

    def tell(self, lines: list[tuple[str, bool]]) -> None:
        """The autopilot's lines: (text, say it out loud) — the rest go into the journal only."""
        for text, loud in lines:
            if loud:
                self.announce(text)
            else:
                self.hud("addLog", "trading", text)

    def announce(self, text: str) -> None:
        self.hud("addLog", "trading", text)
        start, end = settings.load()["voice_hours"]
        if start <= datetime.fromtimestamp(self.clock()).hour < end:
            self.say(text)

    def demo_step(self, prepared: dict, report: dict | None) -> None:
        """DEMO TEST: the demo accounts and the practice account trade by themselves — journal only."""
        with demo._lock:
            book = demo.load()
            lines = demo.step(book, prepared, report)
            demo.save(book)
        for line in lines:
            self.hud("addLog", "trading", line)
        practice.step(prepared)

    def lab_search(self, strategy: str) -> None:
        found = lab.search(strategy, {coin: market.history(coin) for coin in COINS})   # minutes of CPU, no lock
        with self.lock:
            note = lab.start(strategy, found)
        if note:
            self.hud("addLog", "trading", f"Лаборатория: {note}.")

    def testnet(self) -> None:
        self.hud("addLog", "trading", exchange.testnet_check())

    # --- The real account and the chip -----------------------------------------------------------
    def chip(self, network: str | None, state) -> None:
        payload = {"network": network, "positions": [], "demo": []}
        if state:
            payload["positions"] = [
                {"coin": coin, "side": p["side"], "pnl_usd": round(p["pnl"], 2),
                 "pnl_pct": round(p["pnl"] / p["value"] * 100, 2) if p["value"] else 0.0}
                for coin, p in state.positions.items()]
        if settings.demo_on():
            payload["demo"] = [{"name": name, "pct": round((a["balance"] / a["start"] - 1) * 100, 2)}
                               for name, a in demo.load()["accounts"].items()]
        self.hud("setTrading", payload if network or payload["demo"] else None)

    def positions(self) -> None:
        network = settings.network()
        state = exchange.account_state(network)[0] if settings.account(network) else None
        self.chip(network if state else None, state)
        if state is None:
            return
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
        newest = {t["coin"]: t for t in journal.open_trades()}   # the autopilot closes its own trades itself
        for coin in state.positions:
            trade = newest.get(coin)
            if (trade and (not trade.get("auto") or not settings.enabled()) and coin not in self.time_stop_told
                    and now_ms - trade["time"] >= signals.TIME_STOP_HOURS * data.HOUR):
                self.time_stop_told.add(coin)
                name = NAMES.get(coin, coin).lower()
                self.announce(f"Сър, сделката в {name} е отворена от 48 часа — времето ѝ изтече. Кажете "
                              f"„затвори {name}“ и ще я затворя след Вашето одобрение.")
        if settings.enabled() and not exchange.blocked:
            self.tell(autopilot.guard(network, state))
