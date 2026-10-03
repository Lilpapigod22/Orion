"""Indicator series for the trading strategies — pure functions, one value per candle (None while warming up)."""
from collections import deque

Series = list[float | None]


def sma(values: list[float], n: int) -> Series:
    out: Series = []
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= n:
            total -= values[i - n]
        out.append(total / n if i >= n - 1 else None)
    return out


def ema(values: list[float], n: int) -> Series:
    """Exponential average, seeded with the simple average of the first n values."""
    out: Series = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    value = sum(values[:n]) / n
    out[n - 1] = value
    for i in range(n, len(values)):
        value = values[i] * k + value * (1 - k)
        out[i] = value
    return out


def _rsi(gain: float, loss: float) -> float:
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100 - 100 / (1 + gain / loss)


def rsi(values: list[float], n: int = 14) -> Series:
    """Wilder's RSI."""
    out: Series = [None] * len(values)
    if len(values) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / n, losses / n
    out[n] = _rsi(avg_gain, avg_loss)
    for i in range(n + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(change, 0.0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-change, 0.0)) / n
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def true_range(h: list[float], l: list[float], c: list[float]) -> list[float]:  # noqa: E741
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]


def atr(h: list[float], l: list[float], c: list[float], n: int = 14) -> Series:  # noqa: E741
    """Wilder's average true range."""
    out: Series = [None] * len(c)
    if len(c) < n:
        return out
    tr = true_range(h, l, c)
    value = sum(tr[:n]) / n
    out[n - 1] = value
    for i in range(n, len(c)):
        value = (value * (n - 1) + tr[i]) / n
        out[i] = value
    return out


def adx(h: list[float], l: list[float], c: list[float], n: int = 14) -> Series:  # noqa: E741
    """Wilder's ADX — trend strength 0–100 (above ~25: a trend). First value at candle 2n − 1."""
    size = len(c)
    out: Series = [None] * size
    if size < 2 * n + 1:
        return out
    tr = true_range(h, l, c)
    plus = [0.0] + [max(h[i] - h[i - 1], 0.0) if h[i] - h[i - 1] > l[i - 1] - l[i] else 0.0 for i in range(1, size)]
    minus = [0.0] + [max(l[i - 1] - l[i], 0.0) if l[i - 1] - l[i] > h[i] - h[i - 1] else 0.0 for i in range(1, size)]
    tr_s, plus_s, minus_s = sum(tr[1:n + 1]), sum(plus[1:n + 1]), sum(minus[1:n + 1])
    dx = []
    for i in range(n, size):
        if i > n:
            tr_s = tr_s - tr_s / n + tr[i]
            plus_s = plus_s - plus_s / n + plus[i]
            minus_s = minus_s - minus_s / n + minus[i]
        pdi = 100 * plus_s / tr_s if tr_s else 0.0
        mdi = 100 * minus_s / tr_s if tr_s else 0.0
        dx.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
    value = sum(dx[:n]) / n
    out[2 * n - 1] = value
    for k in range(n, len(dx)):
        value = (value * (n - 1) + dx[k]) / n
        out[n + k] = value
    return out


def channel_high(h: list[float], n: int) -> Series:
    """The highest high of the n candles BEFORE each candle (Donchian without the current one)."""
    out: Series = [None] * len(h)
    window: deque[int] = deque()
    for i, value in enumerate(h):
        while window and window[0] < i - n:
            window.popleft()
        if i >= n:
            out[i] = h[window[0]]
        while window and h[window[-1]] <= value:
            window.pop()
        window.append(i)
    return out


def channel_low(l: list[float], n: int) -> Series:  # noqa: E741
    """The lowest low of the n candles BEFORE each candle."""
    out: Series = [None] * len(l)
    window: deque[int] = deque()
    for i, value in enumerate(l):
        while window and window[0] < i - n:
            window.popleft()
        if i >= n:
            out[i] = l[window[0]]
        while window and l[window[-1]] >= value:
            window.pop()
        window.append(i)
    return out


def last_pivot_low(l: list[float], i: int, width: int = 3, lookback: int = 48) -> float | None:  # noqa: E741
    """The most recent swing low confirmed by candle i (the lowest of `width` candles on each side)."""
    for k in range(i - width, max(width, i - lookback) - 1, -1):
        if all(l[k] <= l[j] for j in range(k - width, k + width + 1)):
            return l[k]
    return None


def last_pivot_high(h: list[float], i: int, width: int = 3, lookback: int = 48) -> float | None:
    """The most recent swing high confirmed by candle i."""
    for k in range(i - width, max(width, i - lookback) - 1, -1):
        if all(h[k] >= h[j] for j in range(k - width, k + width + 1)):
            return h[k]
    return None


def levels(h: list[float], l: list[float], i: int, price: float, width: int = 5,  # noqa: E741
           lookback: int = 240) -> tuple[float | None, float | None]:
    """The nearest support (a swing low below the price) and resistance (a swing high above it)."""
    support = resistance = None
    for k in range(i - width, max(width, i - lookback) - 1, -1):
        if all(l[k] <= l[j] for j in range(k - width, k + width + 1)) and l[k] < price:
            support = l[k] if support is None else max(support, l[k])
        if all(h[k] >= h[j] for j in range(k - width, k + width + 1)) and h[k] > price:
            resistance = h[k] if resistance is None else min(resistance, h[k])
    return support, resistance
