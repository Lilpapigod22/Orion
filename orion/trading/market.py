"""Puts a coin's data together for the strategies: history (backtest, lab) or live (forecasts, watch, practice)."""
from . import data, signals

H4, D1 = 4 * data.HOUR, 24 * data.HOUR


def _fear_greed() -> list[tuple[int, int]]:
    try:
        return data.fear_greed()
    except OSError:  # the index is a bonus point, not a reason to fail
        return []


def history(coin: str, params: dict | None = None) -> signals.Prepared:
    """Years of Binance 1h candles (4h and 1d built from them) + Hyperliquid funding."""
    h1 = data.history(coin)
    btc_h4 = data.resample(data.history("BTC"), H4) if coin != "BTC" else None
    return signals.prepare(coin, h1, data.resample(h1, H4), data.resample(h1, D1), data.funding(coin), params,
                           btc_h4=btc_h4, fear_greed=_fear_greed())


def live(coin: str, params: dict | None = None) -> signals.Prepared:
    """Hyperliquid's own candles — the prices sir trades at."""
    h1 = data.live_bars(coin, "1h", 1000)
    h4 = data.live_bars(coin, "4h", 600)
    d1 = data.live_bars(coin, "1d", 400)
    btc_h4 = data.live_bars("BTC", "4h", 600) if coin != "BTC" else None
    return signals.prepare(coin, h1, h4, d1, data.recent_funding(coin), params, btc_h4=btc_h4,
                           fear_greed=_fear_greed())
