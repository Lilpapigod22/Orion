"""
Пазари: акции, индекси, криптовалути, валутни двойки, суровини — цени и технически анализ.

Данните са от Yahoo Finance (без регистрация), а всички индикатори се изчисляват тук, в кода —
малкият модел само ги обяснява с думи. Анализира и CSV файлове, изтеглени от MetaTrader.
"""
import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import pstdev

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0"

# Как го казва сър -> символ в Yahoo Finance.
ALIASES = {
    **dict.fromkeys(["биткойн", "биткоин", "bitcoin", "btc"], "BTC-USD"),
    **dict.fromkeys(["етериум", "етер", "ethereum", "eth"], "ETH-USD"),
    **dict.fromkeys(["солана", "solana", "sol"], "SOL-USD"),
    **dict.fromkeys(["рипъл", "ripple", "xrp"], "XRP-USD"),
    **dict.fromkeys(["доги", "догекойн", "dogecoin", "doge"], "DOGE-USD"),
    **dict.fromkeys(["кардано", "cardano", "ada"], "ADA-USD"),
    **dict.fromkeys(["бинанс", "bnb"], "BNB-USD"),
    **dict.fromkeys(["злато", "златото", "gold"], "GC=F"),
    **dict.fromkeys(["сребро", "среброто", "silver"], "SI=F"),
    **dict.fromkeys(["петрол", "петрола", "нефт", "нефта", "брент", "oil", "brent"], "BZ=F"),
    **dict.fromkeys(["природен газ", "газ", "газа"], "NG=F"),
    **dict.fromkeys(["мед", "медта"], "HG=F"),
    **dict.fromkeys(["евро долар", "eurusd", "eur/usd", "евро/долар"], "EURUSD=X"),
    **dict.fromkeys(["паунд долар", "gbpusd", "gbp/usd", "кабел"], "GBPUSD=X"),
    **dict.fromkeys(["долар йена", "usdjpy", "usd/jpy"], "USDJPY=X"),
    **dict.fromkeys(["евро паунд", "eurgbp", "eur/gbp"], "EURGBP=X"),
    **dict.fromkeys(["долар франк", "usdchf", "usd/chf"], "USDCHF=X"),
    **dict.fromkeys(["s&p", "s&p 500", "sp500", "с и п", "ес енд пи", "есенпи", "с&п"], "^GSPC"),
    **dict.fromkeys(["насдак", "nasdaq"], "^IXIC"),
    **dict.fromkeys(["дау джоунс", "дау", "dow", "dow jones"], "^DJI"),
    **dict.fromkeys(["дакс", "dax"], "^GDAXI"),
    **dict.fromkeys(["никей", "nikkei"], "^N225"),
    **dict.fromkeys(["епъл", "ейпъл", "apple"], "AAPL"),
    **dict.fromkeys(["тесла", "tesla"], "TSLA"),
    **dict.fromkeys(["нвидия", "енвидия", "nvidia"], "NVDA"),
    **dict.fromkeys(["майкрософт", "microsoft"], "MSFT"),
    **dict.fromkeys(["гугъл", "алфабет", "google", "alphabet"], "GOOGL"),
    **dict.fromkeys(["амазон", "amazon"], "AMZN"),
    **dict.fromkeys(["мета", "фейсбук", "meta"], "META"),
    **dict.fromkeys(["нетфликс", "netflix"], "NFLX"),
    **dict.fromkeys(["амд", "amd"], "AMD"),
    **dict.fromkeys(["интел", "intel"], "INTC"),
    **dict.fromkeys(["палантир", "palantir"], "PLTR"),
    **dict.fromkeys(["коинбейс", "coinbase"], "COIN"),
    **dict.fromkeys(["кока-кола", "кока кола", "coca-cola", "coca cola"], "KO"),
    **dict.fromkeys(["пепси", "pepsi"], "PEP"),
    **dict.fromkeys(["макдоналдс", "mcdonalds", "mcdonald's"], "MCD"),
    **dict.fromkeys(["дисни", "disney"], "DIS"),
    **dict.fromkeys(["бъркшир", "berkshire"], "BRK-B"),
    **dict.fromkeys(["виза", "visa"], "V"),
    **dict.fromkeys(["найк", "nike"], "NKE"),
    **dict.fromkeys(["боинг", "boeing"], "BA"),
    **dict.fromkeys(["самсунг", "samsung"], "005930.KS"),
    **dict.fromkeys(["сони", "sony"], "SONY"),
    **dict.fromkeys(["уолмарт", "walmart"], "WMT"),
    **dict.fromkeys(["джей пи морган", "jpmorgan"], "JPM"),
    **dict.fromkeys(["микростратеджи", "стратеджи", "microstrategy"], "MSTR"),
}
# Периоди за таймфреймите: (интервал в Yahoo, обхват, колко свещи да се обединят).
TIMEFRAMES = {"1h": ("1h", "1mo", 1), "4h": ("1h", "6mo", 4), "1d": ("1d", "2y", 1), "1wk": ("1wk", "10y", 1)}


@dataclass
class Series:
    symbol: str
    name: str
    currency: str
    timeframe: str
    time: list[datetime] = field(default_factory=list)
    open: list[float] = field(default_factory=list)
    high: list[float] = field(default_factory=list)
    low: list[float] = field(default_factory=list)
    close: list[float] = field(default_factory=list)
    kind: str = ""  # EQUITY, CRYPTOCURRENCY, CURRENCY, FUTURE, INDEX, FILE


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


# --- Символи ---------------------------------------------------------------------------------
def resolve(asset: str) -> str:
    """Символът в Yahoo Finance за „биткойн“, „Тесла“, „евро долар“, „AAPL“…"""
    from .apps import to_latin
    text = asset.strip().lower().rstrip("?.!")
    text = re.sub(r"^(акциите на|акции на|цената на|курса на|курсът на)\s+", "", text)
    if text in ALIASES:
        return ALIASES[text]
    for alias in sorted(ALIASES, key=len, reverse=True):
        if len(alias) >= 4 and re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text):
            return ALIASES[alias]
    # Вече е символ: „AAPL“ (написан с главни), „btc-usd“, „^gspc“, „eurusd=x“, „gc=f“.
    raw = asset.strip()
    if (raw.isupper() and re.fullmatch(r"[\^A-Z0-9.=\-]{1,12}", raw)) or \
            re.fullmatch(r"\^[a-z0-9]{2,6}|[a-z0-9]{2,6}-[a-z]{3}|[a-z]{6}=x|[a-z]{1,3}=f", text):
        return raw.upper()
    for query in dict.fromkeys([asset, to_latin(asset), to_latin(asset).replace("k", "c")]):
        try:
            found = _get_json("https://query2.finance.yahoo.com/v1/finance/search?quotesCount=1&newsCount=0&q="
                              + urllib.parse.quote(query)).get("quotes", [])
        except OSError:
            continue
        if found:
            return found[0]["symbol"]
    raise ValueError(f"не намирам актив „{asset}“ на борсите — кажете името на английски или символа")


# --- Данни -------------------------------------------------------------------------------------
def history(asset: str, timeframe: str = "1d") -> Series:
    symbol = resolve(asset)
    interval, span, merge = TIMEFRAMES.get(timeframe, TIMEFRAMES["1d"])
    data = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
                     f"?range={span}&interval={interval}")
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result or not result.get("timestamp"):
        raise ValueError(f"няма данни за {symbol}")
    meta, quote = result["meta"], result["indicators"]["quote"][0]
    series = Series(symbol, meta.get("longName") or meta.get("shortName") or symbol, meta.get("currency", ""),
                    timeframe, kind=meta.get("instrumentType", ""))
    rows = zip(result["timestamp"], quote["open"], quote["high"], quote["low"], quote["close"])
    for ts, o, h, lo, c in rows:
        if None in (o, h, lo, c):
            continue
        series.time.append(datetime.fromtimestamp(ts, timezone.utc).astimezone().replace(tzinfo=None))
        series.open.append(o); series.high.append(h); series.low.append(lo); series.close.append(c)  # noqa: E702
    live = meta.get("regularMarketPrice")
    if live and series.close:  # последната свещ — с текущата цена
        series.close[-1] = live
    return _merge(series, merge) if merge > 1 else series


def _merge(series: Series, n: int) -> Series:
    """Часови свещи -> 4-часови (по часовете 0, 4, 8…)."""
    merged = Series(series.symbol, series.name, series.currency, series.timeframe, kind=series.kind)
    bucket: list[int] = []
    for i, t in enumerate(series.time):
        if bucket and (t.hour // n != series.time[bucket[0]].hour // n or t.date() != series.time[bucket[0]].date()):
            _flush(series, merged, bucket)
            bucket = []
        bucket.append(i)
    if bucket:
        _flush(series, merged, bucket)
    return merged


def _flush(src: Series, dst: Series, idx: list[int]) -> None:
    dst.time.append(src.time[idx[0]])
    dst.open.append(src.open[idx[0]])
    dst.high.append(max(src.high[i] for i in idx))
    dst.low.append(min(src.low[i] for i in idx))
    dst.close.append(src.close[idx[-1]])


def load_csv(path: Path) -> Series:
    """CSV от MetaTrader или друг източник: дата[ час], отваряне, максимум, минимум, затваряне…"""
    raw = Path(path).read_bytes()
    encoding = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    lines = [ln.strip() for ln in raw.decode(encoding, errors="replace").splitlines() if ln.strip()]
    delimiter = max([",", ";", "\t"], key=lambda d: lines[0].count(d))
    series = Series(Path(path).stem.upper(), Path(path).stem, "", "файл", kind="FILE")
    for line in lines:
        cells = [c.strip().strip('"') for c in line.split(delimiter)]
        stamp = cells[0]
        values = cells[1:]
        if len(cells) > 5 and re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", cells[1]):  # отделна колона за час
            stamp, values = f"{cells[0]} {cells[1]}", cells[2:]
        try:
            moment = datetime.strptime(re.sub(r"[./]", "-", stamp)[:16].strip(), "%Y-%m-%d %H:%M") if " " in stamp \
                else datetime.strptime(re.sub(r"[./]", "-", stamp)[:10], "%Y-%m-%d")
            o, h, lo, c = (float(v.replace(",", ".")) for v in values[:4])
        except ValueError:
            continue  # заглавен ред или повреден ред
        series.time.append(moment)
        series.open.append(o); series.high.append(h); series.low.append(lo); series.close.append(c)  # noqa: E702
    if len(series.close) < 30:
        raise ValueError("във файла няма достатъчно редове с цени (дата, отваряне, максимум, минимум, затваряне)")
    if len(series.time) > 2:
        step = (series.time[-1] - series.time[-2]).total_seconds() / 3600
        series.timeframe = {1: "1h", 4: "4h", 24: "1d"}.get(round(step), f"{step:g}h")
    return series


# --- Индикатори ------------------------------------------------------------------------------
def sma(values: list[float], n: int) -> list[float | None]:
    out, total = [], 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        out.append(total / n if i >= n - 1 else None)
    return out


def ema(values: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for v in values:
        out.append(v if not out else v * k + out[-1] * (1 - k))
    return out


def rsi(values: list[float], n: int = 14) -> float | None:
    if len(values) <= n:
        return None
    gains = [max(0.0, values[i] - values[i - 1]) for i in range(1, len(values))]
    losses = [max(0.0, values[i - 1] - values[i]) for i in range(1, len(values))]
    avg_gain, avg_loss = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, lo in zip(gains[n:], losses[n:]):  # изглаждане на Уайлдър
        avg_gain, avg_loss = (avg_gain * (n - 1) + g) / n, (avg_loss * (n - 1) + lo) / n
    return 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)


def atr(s: Series, n: int = 14) -> float | None:
    if len(s.close) <= n:
        return None
    ranges = [max(s.high[i] - s.low[i], abs(s.high[i] - s.close[i - 1]), abs(s.low[i] - s.close[i - 1]))
              for i in range(1, len(s.close))]
    value = sum(ranges[:n]) / n
    for r in ranges[n:]:
        value = (value * (n - 1) + r) / n
    return value


def levels(s: Series, lookback: int = 120, width: int = 5) -> tuple[float | None, float | None]:
    """Най-близката подкрепа (дъно) под цената и съпротива (връх) над нея — от последните свещи."""
    lows, highs = s.low[-lookback:], s.high[-lookback:]
    price = s.close[-1]
    pivots_low = [lows[i] for i in range(width, len(lows) - width)
                  if lows[i] == min(lows[i - width:i + width + 1])]
    pivots_high = [highs[i] for i in range(width, len(highs) - width)
                   if highs[i] == max(highs[i - width:i + width + 1])]
    support = max((v for v in pivots_low if v < price), default=min(lows) if min(lows) < price else None)
    resistance = min((v for v in pivots_high if v > price), default=max(highs) if max(highs) > price else None)
    return support, resistance


# --- Анализ ------------------------------------------------------------------------------------
def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1000:
        return f"{value:,.0f}".replace(",", " ")
    return f"{value:.2f}" if abs(value) >= 10 else f"{value:.5g}"


def _change(s: Series, bars: int) -> float | None:
    if len(s.close) <= bars:
        return None
    return (s.close[-1] / s.close[-1 - bars] - 1) * 100


def analyze(s: Series) -> dict:
    """Всички числа за анализа — после report() ги подрежда в текст, а UI ги рисува."""
    c = s.close
    price = c[-1]
    sma20, sma50, sma200 = sma(c, 20), sma(c, 50), sma(c, 200)
    macd_line = [a - b for a, b in zip(ema(c, 12), ema(c, 26))]
    signal = ema(macd_line, 9)
    boll_mid = sma20[-1]
    boll_dev = pstdev(c[-20:]) if len(c) >= 20 else None
    returns = [math.log(c[i] / c[i - 1]) for i in range(max(1, len(c) - 90), len(c)) if c[i - 1] > 0]
    per_year = {"1d": 365 if s.kind == "CRYPTOCURRENCY" else 252, "1wk": 52, "4h": 6 * 252, "1h": 24 * 252}
    peak, drawdown = c[0], 0.0
    for v in c:
        peak = max(peak, v)
        drawdown = min(drawdown, v / peak - 1)
    support, resistance = levels(s)
    daily = s.timeframe == "1d"
    week = 7 if s.kind == "CRYPTOCURRENCY" else 5
    per_day = {"1h": 24, "4h": 6}.get(s.timeframe, 1)  # за часовите и 4-часовите свещи
    changes = {"1 свещ": _change(s, 1), "ден": _change(s, per_day), "седмица": _change(s, per_day * 5),
               "месец": _change(s, per_day * 21)}
    if daily:
        changes = {"ден": _change(s, 1), "седмица": _change(s, week), "месец": _change(s, 21 if week == 5 else 30),
                   "3 месеца": _change(s, 63 if week == 5 else 90), "година": _change(s, 252 if week == 5 else 365)}
    cross = None
    for i in range(len(c) - 1, max(200, len(c) - 60), -1):  # пресичане на SMA50/SMA200 в последните 60 свещи
        if sma50[i] and sma200[i] and sma50[i - 1] and sma200[i - 1]:
            if (sma50[i] > sma200[i]) != (sma50[i - 1] > sma200[i - 1]):
                cross = ("златен кръст" if sma50[i] > sma200[i] else "кръст на смъртта", s.time[i])
                break
    return {
        "price": price, "sma20": sma20[-1], "sma50": sma50[-1], "sma200": sma200[-1],
        "rsi": rsi(c), "macd": macd_line[-1], "signal": signal[-1], "macd_prev": macd_line[-2] - signal[-2],
        "boll_up": boll_mid + 2 * boll_dev if boll_mid and boll_dev else None,
        "boll_low": boll_mid - 2 * boll_dev if boll_mid and boll_dev else None,
        "atr": atr(s), "vol": pstdev(returns) * math.sqrt(per_year.get(s.timeframe, 252)) * 100 if len(returns) > 10 else None,
        "high": max(s.high[-252:]), "low": min(s.low[-252:]), "drawdown": drawdown * 100,
        "support": support, "resistance": resistance, "changes": changes, "cross": cross,
        "sma20_line": sma20, "sma50_line": sma50,
    }


def report(s: Series, a: dict) -> str:
    """Анализът като текст за модела — числата и какво значат."""
    price = a["price"]
    notes, score = [], 0
    for label, level in (("SMA50", a["sma50"]), ("SMA200", a["sma200"])):
        if level:
            above = price > level
            score += 1 if above else -1
            notes.append(f"цената е {'над' if above else 'под'} {label} ({_fmt(level)})")
    if a["sma50"] and a["sma200"]:
        notes.append("SMA50 е " + ("над" if a["sma50"] > a["sma200"] else "под") + " SMA200 — дългосрочен тренд "
                     + ("възходящ" if a["sma50"] > a["sma200"] else "низходящ"))
    if a["cross"]:
        notes.append(f"{a['cross'][0]} на {a['cross'][1]:%d.%m.%Y}")
    rsi_value = a["rsi"]
    if rsi_value is not None:
        state = "свръхкупен (>70)" if rsi_value > 70 else "свръхпродаден (<30)" if rsi_value < 30 else "неутрален"
        notes.append(f"RSI(14) = {rsi_value:.0f} — {state}")
        score += -1 if rsi_value > 70 else 1 if rsi_value < 30 else 0
    histogram = a["macd"] - a["signal"]
    macd_state = "над сигналната линия (бичи импулс)" if histogram > 0 else "под сигналната линия (мечи импулс)"
    if (histogram > 0) != (a["macd_prev"] > 0):
        macd_state += ", току-що я пресече"
    notes.append(f"MACD е {macd_state}")
    score += 1 if histogram > 0 else -1
    if a["boll_up"] and a["boll_low"]:
        where = ("над горната лента" if price > a["boll_up"] else "под долната лента" if price < a["boll_low"]
                 else "между лентите")
        notes.append(f"Болинджър (20,2): {_fmt(a['boll_low'])}–{_fmt(a['boll_up'])}, цената е {where}")
    bias = "възходящ" if score >= 2 else "низходящ" if score <= -2 else "неутрален/смесен"
    changes = ", ".join(f"{k} {v:+.1f}%" for k, v in a["changes"].items() if v is not None)
    frame = {"1h": "часови", "4h": "4-часови", "1d": "дневни", "1wk": "седмични"}.get(s.timeframe, s.timeframe)
    lines = [
        f"Технически анализ на {s.name} ({s.symbol}), {frame} свещи до {s.time[-1]:%d.%m.%Y %H:%M}.",
        f"Цена: {_fmt(price)}{' ' + s.currency if s.currency else ''}. Промяна: {changes}.",
        f"Диапазон за периода: {_fmt(a['low'])}–{_fmt(a['high'])}; най-голям спад от връх: {a['drawdown']:.0f}%.",
        f"Най-близка подкрепа: {_fmt(a['support'])}; съпротива: {_fmt(a['resistance'])}.",
        "Сигнали: " + "; ".join(notes) + ".",
        f"ATR(14): {_fmt(a['atr'])}" + (f"; годишна волатилност ≈ {a['vol']:.0f}%" if a["vol"] else "") + ".",
        f"Общ технически уклон: {bias}.",
    ]
    return "\n".join(lines)


def chart_data(s: Series, a: dict, points: int = 120) -> dict:
    """Данните за графиката в прозореца — последните `points` свещи."""
    start = max(0, len(s.close) - points)
    return {
        "symbol": s.symbol, "name": s.name, "currency": s.currency, "timeframe": s.timeframe,
        "time": [t.strftime("%d.%m") if s.timeframe in ("1d", "1wk") else t.strftime("%d.%m %H:%M")
                 for t in s.time[start:]],
        "close": [round(v, 6) for v in s.close[start:]],
        "sma20": [None if v is None else round(v, 6) for v in a["sma20_line"][start:]],
        "sma50": [None if v is None else round(v, 6) for v in a["sma50_line"][start:]],
        "support": a["support"], "resistance": a["resistance"],
        "change": next((v for v in a["changes"].values() if v is not None), 0),
    }


def quote(asset: str) -> tuple[str, float, float, str]:
    """(име, цена, промяна за деня в %, валута)."""
    symbol = resolve(asset)
    meta = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
                     f"?range=5d&interval=1d")["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    previous = meta.get("chartPreviousClose") or meta.get("previousClose") or price
    change = meta.get("regularMarketChangePercent")
    if change is None:
        change = (price / previous - 1) * 100 if previous else 0.0
    return meta.get("longName") or meta.get("shortName") or symbol, price, change, meta.get("currency", "")


def price_file(name: str) -> Path:
    """CSV файл с цени по име — на работния плот, в Документи или Изтегляния."""
    if Path(name.strip('"')).is_file():
        return Path(name.strip('"'))
    home = Path.home()
    wanted = name.lower().replace(".csv", "").strip()
    for folder in (home / "Desktop", home / "Documents", home / "Downloads", home / "OneDrive" / "Desktop"):
        for file in folder.glob("*.csv"):
            if wanted in file.stem.lower():
                return file
    raise FileNotFoundError(f"не намирам CSV файл „{name}“ на работния плот, в Документи или Изтегляния")
