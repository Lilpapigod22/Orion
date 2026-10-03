import json
import re

import pytest

from orion.trading import data
from orion.trading.data import HOUR, Bars


def hourly(n, start=0, close=100.0):
    bars = Bars(HOUR)
    for k in range(n):
        bars.add(start + k * HOUR, close + k, close + k + 2, close + k - 1, close + k + 1, 10.0)
    return bars


def test_resample_builds_aligned_4h_candles_and_drops_the_unfinished_one():
    bars = hourly(10)                                   # 00:00 … 09:00 -> 4h at 00:00 and 04:00; 08:00 unfinished
    four = data.resample(bars, 4 * HOUR)
    assert four.t == [0, 4 * HOUR]
    assert four.o == [100.0, 104.0]
    assert four.h == [105.0, 109.0]
    assert four.l == [99.0, 103.0]
    assert four.c == [104.0, 108.0]
    assert four.v == [40.0, 40.0]


def test_bars_json_round_trip_and_since():
    bars = hourly(5)
    again = Bars.from_json(json.loads(json.dumps(bars.to_json())))
    assert again.t == bars.t and again.c == bars.c and again.interval == HOUR
    assert again.since(3 * HOUR).t == [3 * HOUR, 4 * HOUR]
    assert bars.end(0) == HOUR


def test_live_bars_drop_the_candle_that_is_still_open(monkeypatch):
    now = 10 * HOUR + 1800_000
    rows = [{"t": k * HOUR, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "3"} for k in range(11)]
    monkeypatch.setattr(data, "_now", lambda: now)
    monkeypatch.setattr(data, "_post", lambda body: rows)
    bars = data.live_bars("BTC", "1h", 20)
    assert len(bars) == 10 and bars.t[-1] == 9 * HOUR and bars.c[0] == 1.5


def fake_binance(calls, clock):
    def get(url):
        start = int(re.search(r"startTime=(\d+)", url)[1])
        calls.append(start)
        rows, t = [], start
        while t <= clock() and len(rows) < 1000:       # Binance also returns the unfinished hour
            rows.append([t, "1", "2", "0.5", "1.5", "10"])
            t += HOUR
        return rows
    return get


def test_history_downloads_once_then_only_the_tail(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path)
    now = data.HISTORY_START + 2500 * HOUR + 1800_000
    calls = []
    monkeypatch.setattr(data, "_now", lambda: now)
    monkeypatch.setattr(data, "_get", fake_binance(calls, lambda: now))
    bars = data.history("SOL")
    assert len(bars) == 2500 and bars.t[0] == data.HISTORY_START
    assert calls == [data.HISTORY_START, data.HISTORY_START + 1000 * HOUR, data.HISTORY_START + 2000 * HOUR]
    calls.clear()
    now += 3 * HOUR
    again = data.history("SOL")
    assert len(again) == 2503
    assert calls == [data.HISTORY_START + 2500 * HOUR]


def test_funding_pages_and_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(data, "PAGE_PAUSE", 0)
    pages = []

    def post(body):
        pages.append(body["startTime"])
        start = body["startTime"]
        count = 500 if len(pages) == 1 else 10
        return [{"coin": "BTC", "fundingRate": "0.0001", "premium": "0", "time": start + k * HOUR}
                for k in range(count)]

    monkeypatch.setattr(data, "_post", post)
    rows = data.funding("BTC")
    assert len(rows) == 510 and rows[0] == (data.HISTORY_START, 0.0001)
    assert pages == [data.HISTORY_START, data.HISTORY_START + 499 * HOUR + 1]
    assert (tmp_path / "BTC_funding.json").exists()


def test_assets_reads_the_three_coins(monkeypatch):
    meta = {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
                         {"name": "DOGE", "szDecimals": 0, "maxLeverage": 10},
                         {"name": "SOL", "szDecimals": 2, "maxLeverage": 20}]}
    ctx = [{"funding": "0.00001", "openInterest": "100", "premium": "-0.0003", "markPx": "84465.0", "midPx": "84468.5"},
           {"funding": "0", "openInterest": "1", "premium": "0", "markPx": "0.1", "midPx": "0.1"},
           {"funding": "0.00002", "openInterest": "5", "premium": "0", "markPx": "118.4", "midPx": None}]
    monkeypatch.setattr(data, "_post", lambda body: [meta, ctx])
    found = data.assets()
    assert set(found) == {"BTC", "SOL"}
    assert found["BTC"].mid == 84468.5 and found["BTC"].sz_decimals == 5 and found["BTC"].max_leverage == 40
    assert found["SOL"].mid == 118.4                     # no mid -> the mark price


def test_open_interest_snapshots_are_appended_and_capped(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "OI_FILE", tmp_path / "oi.json")
    monkeypatch.setattr(data, "OI_LIMIT", 2)
    monkeypatch.setattr(data, "_now", lambda: 5)
    asset = data.Asset("BTC", 1, 1, 0, 123.0, 0, 5, 40)
    for _ in range(3):
        data.record_open_interest({"BTC": asset})
    rows = json.loads((tmp_path / "oi.json").read_text(encoding="utf-8"))
    assert rows == [{"time": 5, "BTC": 123.0}, {"time": 5, "BTC": 123.0}]
