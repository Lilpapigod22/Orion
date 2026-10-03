import pytest

from orion.trading import indicators as ind


def test_sma():
    assert ind.sma([1, 2, 3, 4, 5], 2) == [None, 1.5, 2.5, 3.5, 4.5]


def test_ema_is_seeded_with_the_simple_average():
    out = ind.ema([1.0, 2.0, 3.0, 4.0], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)              # 4 * 0.5 + 2 * 0.5
    assert ind.ema([5.0] * 30, 10)[-1] == pytest.approx(5.0)


def test_rsi_extremes_and_balance():
    assert ind.rsi([float(x) for x in range(30)])[-1] == pytest.approx(100.0)
    assert ind.rsi([float(30 - x) for x in range(30)])[-1] == pytest.approx(0.0)
    zigzag = [100.0 + (1 if k % 2 else 0) for k in range(60)]
    assert ind.rsi(zigzag)[-1] == pytest.approx(50.0, abs=3)
    assert ind.rsi([1.0] * 10)[-1] is None


def test_atr_of_constant_range():
    n = 40
    out = ind.atr([12.0] * n, [10.0] * n, [11.0] * n, 14)
    assert out[12] is None and out[13] == pytest.approx(2.0) and out[-1] == pytest.approx(2.0)


def test_adx_is_high_in_a_trend_and_low_in_chop():
    n = 80
    up = ind.adx([k + 1.0 for k in range(n)], [float(k) for k in range(n)], [k + 0.5 for k in range(n)])
    assert up[-1] > 50
    h = [11.0 if k % 2 == 0 else 10.0 for k in range(n)]
    l = [10.0 if k % 2 == 0 else 9.0 for k in range(n)]
    chop = ind.adx(h, l, [(a + b) / 2 for a, b in zip(h, l)])
    assert chop[-1] < 20
    assert up[26] is None and up[27] is not None


def test_channels_exclude_the_current_candle():
    assert ind.channel_high([1.0, 5.0, 2.0, 3.0, 9.0], 2) == [None, None, 5.0, 5.0, 3.0]
    assert ind.channel_low([5.0, 1.0, 4.0, 3.0, 0.0], 2) == [None, None, 1.0, 1.0, 3.0]


def test_pivots_need_confirmation():
    lows = [5.0, 4.0, 3.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert ind.last_pivot_low(lows, 8, width=2) == 2.0
    assert ind.last_pivot_low(lows, 4, width=2) is None   # the low at 3 is not confirmed yet
    highs = [1.0, 2.0, 3.0, 9.0, 3.0, 2.0, 1.0, 1.5]
    assert ind.last_pivot_high(highs, 7, width=2) == 9.0


def test_levels_pick_the_nearest_support_and_resistance():
    h = [10, 12, 10, 9, 10, 15, 10, 9, 10, 11, 10, 10, 10, 10, 10]
    l = [8, 9, 8, 5, 8, 9, 8, 7, 8, 9, 8, 8, 8, 8, 8]
    support, resistance = ind.levels([float(x) for x in h], [float(x) for x in l], 14, 10.5, width=1)
    assert support == 8.0 and resistance == 11.0
