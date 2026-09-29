"""
Пазари: акции, индекси, криптовалути, валутни двойки и суровини — цени, технически анализ,
преглед на пазарите и анализ на CSV файлове от MetaTrader.

Анализите са информация, не инвестиционен съвет — Орион го казва.
"""
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from jarvis import jarvis_tool, markets, web

DISCLAIMER = "(Кажи накратко какво значи и напомни, че това е технически анализ, не инвестиционен съвет.)"
# Последната графика — приложението я показва в журнала (app.py -> hud.showChart).
last_chart: dict | None = None


def _news(name: str) -> str:
    try:
        hits = web.search(name, news=True, max_results=3, region="wt-wt")
    except Exception:  # noqa: BLE001 — анализът е ценен и без новини
        return ""
    if not hits:
        return ""
    return "\nПоследни новини: " + " | ".join(f"{h['title']} ({h['date']})" for h in hits)


@jarvis_tool
def market_price(asset: str) -> str:
    """Текущата цена и промяната за деня на акция, индекс, криптовалута, валутна двойка или суровина.

    Args:
        asset: Име или символ, напр. "биткойн", "Тесла", "злато", "евро долар", "AAPL".
    """
    name, price, change, currency = markets.quote(asset)
    return f"{name}: {markets._fmt(price)} {currency} ({change:+.2f}% за деня)."


@jarvis_tool
def analyze_market(asset: str, timeframe: str = "1d") -> str:
    """Технически анализ на акция, криптовалута, валутна двойка, индекс или суровина: тренд, средни
    линии, RSI, MACD, Болинджър, подкрепа и съпротива, волатилност и последните новини.

    Args:
        asset: Име или символ, напр. "биткойн", "Nvidia", "злато", "евро долар".
        timeframe: Таймфрейм: "1h", "4h", "1d" (по подразбиране) или "1wk".
    """
    global last_chart
    series = markets.history(asset, timeframe)
    analysis = markets.analyze(series)
    last_chart = markets.chart_data(series, analysis)
    return markets.report(series, analysis) + _news(series.name) + "\n" + DISCLAIMER


@jarvis_tool
def analyze_price_file(file_name: str) -> str:
    """Технически анализ на CSV файл с цени (напр. изтеглен от MetaTrader) — от работния плот,
    Документи или Изтегляния.

    Args:
        file_name: Името на файла или част от него, напр. "EURUSDH4".
    """
    global last_chart
    series = markets.load_csv(markets.price_file(file_name))
    analysis = markets.analyze(series)
    last_chart = markets.chart_data(series, analysis)
    return markets.report(series, analysis) + "\n" + DISCLAIMER


_OVERVIEW = {
    "Индекси": {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow Jones": "^DJI", "DAX": "^GDAXI"},
    "Крипто": {"Биткойн": "BTC-USD", "Етериум": "ETH-USD", "Солана": "SOL-USD"},
    "Валути": {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X"},
    "Суровини": {"Злато": "GC=F", "Петрол Брент": "BZ=F", "Сребро": "SI=F"},
}


@jarvis_tool
def market_overview() -> str:
    """Преглед на пазарите днес: основните индекси, криптовалути, валути, злато и петрол."""
    symbols = [(group, label, symbol) for group, items in _OVERVIEW.items() for label, symbol in items.items()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        quotes = list(pool.map(lambda item: _safe_quote(item[2]), symbols))
    parts: dict[str, list[str]] = {}
    for (group, label, _), found in zip(symbols, quotes):
        if found:
            _, price, change, _ = found
            parts.setdefault(group, []).append(f"{label} {markets._fmt(price)} ({change:+.1f}%)")
    if not parts:
        raise ConnectionError("няма връзка с пазарните данни")
    return "Пазарите днес — " + "; ".join(f"{g}: {', '.join(items)}" for g, items in parts.items()) + "."


def _safe_quote(symbol: str):
    try:
        return markets.quote(symbol)
    except Exception:  # noqa: BLE001 — един липсващ актив не проваля прегледа
        return None


@jarvis_tool
def crypto_market() -> str:
    """Крипто пазарът сега: най-големите криптовалути и кои растат и падат най-много за 24 часа."""
    request = urllib.request.Request(
        "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50",
        headers={"User-Agent": markets.USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        coins = json.load(response)
    top = ", ".join(f"{c['name']} ${markets._fmt(c['current_price'])} ({c['price_change_percentage_24h'] or 0:+.1f}%)"
                    for c in coins[:8])
    movers = sorted(coins, key=lambda c: c["price_change_percentage_24h"] or 0)
    down = ", ".join(f"{c['name']} {c['price_change_percentage_24h']:+.1f}%" for c in movers[:3])
    up = ", ".join(f"{c['name']} {c['price_change_percentage_24h']:+.1f}%" for c in movers[-3:][::-1])
    total = sum(c.get("market_cap") or 0 for c in coins) / 1e12
    return (f"Най-големите: {top}. Най-много растат (от първите 50): {up}. Най-много падат: {down}. "
            f"Обща капитализация на първите 50: ≈ {total:.2f} трилиона долара.")
