"""
„Симулирай 1000 долара за последната година“: the strategies replayed on history across the three coins with
compounding — one position per coin, the risk sized on the realised balance at each entry, fees, slippage and
funding as in the backtest. Only the strategies that passed the honest check, unless all_signals. Results are
in R, so a live trade's leverage cap is not applied here.
"""
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime

from . import COINS, backtest, data, market, signals


@dataclass
class Result:
    start: float
    final: float
    trades: int
    wins: int
    max_drawdown_pct: float
    months: dict = field(default_factory=dict)      # "MM.YYYY" -> % change in that month
    days: int = 365
    strategies: dict = field(default_factory=dict)  # coin -> the strategies used

    @property
    def return_pct(self) -> float:
        return (self.final / self.start - 1) * 100


def run(balance: float, days: int = 365, risk_pct: float = 2.0, all_signals: bool = False,
        report: dict | None = None, markets: dict | None = None) -> Result:
    markets = markets if markets is not None else {coin: market.history(coin) for coin in COINS}
    trades, used = [], {}
    for coin, p in markets.items():
        end = p.h1.end(len(p.h1) - 1)
        start = bisect_left(p.h1.t, end - days * 24 * data.HOUR)
        used[coin] = [s for s in signals.STRATEGIES if all_signals or backtest.is_enabled(report, coin, s)]
        for strategy in used[coin]:
            trades += backtest.simulate(p, strategy, start, len(p.h1))
    trades.sort(key=lambda t: (t.entry_time, t.coin))

    cash = peak = float(balance)
    drawdown = 0.0
    busy: dict[str, int] = {}
    pending: list[tuple[int, object, float]] = []   # (exit time, trade, risk in $)
    months: dict[str, list[float]] = {}             # month -> [balance at its first exit, P/L]
    taken = wins = 0

    def realise(until: float) -> None:
        nonlocal cash, peak, drawdown, wins
        for item in sorted((x for x in pending if x[0] <= until), key=lambda x: x[0]):
            pending.remove(item)
            exit_time, trade, risk_usd = item
            month = months.setdefault(datetime.fromtimestamp(exit_time / 1000).strftime("%m.%Y"), [cash, 0.0])
            pnl = trade.r * risk_usd
            month[1] += pnl
            cash += pnl
            wins += pnl > 0
            peak = max(peak, cash)
            drawdown = max(drawdown, (peak - cash) / peak * 100 if peak > 0 else 0.0)

    for trade in trades:
        if busy.get(trade.coin, -1) > trade.entry_time:
            continue  # one position per coin
        realise(trade.entry_time)
        if cash <= 0:
            break
        busy[trade.coin] = trade.exit_time
        pending.append((trade.exit_time, trade, cash * risk_pct / 100))
        taken += 1
    realise(float("inf"))
    return Result(float(balance), cash, taken, wins, drawdown,
                  {m: pnl / first * 100 for m, (first, pnl) in months.items()}, days, used)
