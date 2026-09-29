"""
За търговеца: сравнение на активи, най-големите победители и губещи на борсата, индексът
„страх и алчност“, криптовалути в евро/лева, известия при цена и портфейл с печалба/загуба.
"""
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from jarvis import alerts, jarvis_tool, markets

BGN_PER_EUR = 1.95583


@jarvis_tool
def compare_assets(assets: str) -> str:
    """Сравнява представянето на различни активи за кратки периоди като месец, 3 месеца или година.
    Използва се при сравнение на конкретни пари (напр. „Сравни биткойна и златото", „Кой е по-добър:
    акциите или доларът?").

    Args:
        assets: Активите, разделени със запетаи, напр. "биткойн, злато, S&P 500".
    """
    names = [a.strip() for a in assets.replace(" и ", ",").split(",") if a.strip()][:6]

    def row(asset: str) -> str:
        try:
            s = markets.history(asset, "1d")
        except Exception as e:  # noqa: BLE001
            return f"{asset}: няма данни ({e})"
        week = 7 if s.kind == "CRYPTOCURRENCY" else 5
        parts = [f"{label} {markets._change(s, bars):+.1f}%" for label, bars in
                 (("месец", week * 4 + week // 5), ("3 месеца", week * 13), ("година", 365 if week == 7 else 252))
                 if markets._change(s, bars) is not None]
        return f"{s.name}: {', '.join(parts)}"

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(row, names))
    return "Сравнение — " + "; ".join(rows) + "."


def _screener(kind: str) -> list[dict]:
    request = urllib.request.Request(
        f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds={kind}&count=6",
        headers={"User-Agent": markets.USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)["finance"]["result"][0]["quotes"]


@jarvis_tool
def top_stock_movers() -> str:
    """Акциите в САЩ, които днес растат и падат най-много."""
    rows = []
    for kind, title in (("day_gainers", "Растат"), ("day_losers", "Падат")):
        quotes = _screener(kind)
        rows.append(f"{title}: " + ", ".join(
            f"{q.get('shortName') or q['symbol']} ({q['symbol']}) {q.get('regularMarketChangePercent', 0):+.1f}%"
            for q in quotes[:5]))
    return "; ".join(rows) + "."


@jarvis_tool
def crypto_fear_greed() -> str:
    """Индексът „страх и алчност“ на крипто пазара (0 — паника, 100 — еуфория) и промяната му."""
    data = markets._get_json("https://api.alternative.me/fng/?limit=8")["data"]
    labels = {"Extreme Fear": "силен страх", "Fear": "страх", "Neutral": "неутрално", "Greed": "алчност",
              "Extreme Greed": "силна алчност"}
    now, week = data[0], data[-1]
    return (f"Индексът е {now['value']} — {labels.get(now['value_classification'], now['value_classification'])} "
            f"(преди седмица: {week['value']}, {labels.get(week['value_classification'], '')}).")


@jarvis_tool
def convert_crypto(amount: float, coin: str, currency: str = "EUR") -> str:
    """Колко струват криптовалути в евро, лева или долари. За „колко са 0.5 биткойна в евро“.

    Args:
        amount: Количеството, напр. 0.5.
        coin: Криптовалутата, напр. "биткойн" или "ETH".
        currency: В каква валута: EUR (по подразбиране), BGN или USD.
    """
    name, price_usd, _, _ = markets.quote(coin)
    target = currency.upper().replace("ЛЕВА", "BGN").replace("ЕВРО", "EUR")
    usd = amount * price_usd
    if target == "USD":
        value = usd
    else:
        eur_per_usd = markets._get_json("https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR")["rates"]["EUR"]
        value = usd * eur_per_usd * (BGN_PER_EUR if target == "BGN" else 1)
    return f"{amount:g} {name} = {markets._fmt(value)} {target if target != 'BGN' else 'лева'} (цена {markets._fmt(price_usd)} USD)."


@jarvis_tool
def set_price_alert(asset: str, price: float) -> str:
    """Известие при цена: Митко казва, когато актив надмине или падне под дадена цена.

    Args:
        asset: Активът, напр. "биткойн" или "евро долар".
        price: Цената, при която да известя.
    """
    name, current, _, currency = markets.quote(asset)
    symbol = markets.resolve(asset)
    direction = "above" if price > current else "below"
    items = alerts.load(alerts.ALERTS)
    items.append({"symbol": symbol, "name": name, "price": price, "direction": direction})
    alerts.save(alerts.ALERTS, items)
    word = "надмине" if direction == "above" else "падне под"
    return f"Ще Ви кажа, когато {name} {word} {markets._fmt(price)} (сега е {markets._fmt(current)} {currency})."


@jarvis_tool
def list_price_alerts() -> str:
    """Кои известия за цени чакат."""
    items = alerts.load(alerts.ALERTS)
    if not items:
        return "Няма известия за цени."
    return "Известия: " + "; ".join(
        f"{i['name']} {'над' if i['direction'] == 'above' else 'под'} {markets._fmt(i['price'])}" for i in items) + "."


@jarvis_tool
def cancel_price_alert(asset: str = "") -> str:
    """Маха известие за цена (или всички).

    Args:
        asset: Активът (празно — всички).
    """
    items = alerts.load(alerts.ALERTS)
    symbol = markets.resolve(asset) if asset.strip() else None
    kept = [i for i in items if symbol and i["symbol"] != symbol]
    alerts.save(alerts.ALERTS, kept)
    return f"Махнах {len(items) - len(kept)} известия."


@jarvis_tool
def portfolio_add(asset: str, amount: float, buy_price: float = 0) -> str:
    """Добавя актив в портфейла на сър (колко има и на каква цена е купил).

    Args:
        asset: Активът, напр. "биткойн" или "Apple".
        amount: Количеството (брой акции, монети…).
        buy_price: Цената на покупка (0 — текущата).
    """
    name, current, _, currency = markets.quote(asset)
    items = alerts.load(alerts.PORTFOLIO)
    items.append({"symbol": markets.resolve(asset), "name": name, "amount": amount,
                  "buy_price": buy_price or current, "currency": currency})
    alerts.save(alerts.PORTFOLIO, items)
    return f"Добавих {amount:g} {name} на цена {markets._fmt(buy_price or current)} {currency} в портфейла."


@jarvis_tool
def portfolio_show() -> str:
    """Портфейлът на сър: стойност сега, печалба или загуба за всеки актив и общо."""
    items = alerts.load(alerts.PORTFOLIO)
    if not items:
        return "Портфейлът е празен — добавете активи с „добави 0.1 биткойна в портфейла“."
    with ThreadPoolExecutor(max_workers=6) as pool:
        prices = list(pool.map(lambda i: markets.quote(i["symbol"])[1], items))
    rows, totals = [], {}
    for item, price in zip(items, prices):
        value, cost = item["amount"] * price, item["amount"] * item["buy_price"]
        change = (value / cost - 1) * 100 if cost else 0
        rows.append(f"{item['name']}: {markets._fmt(value)} {item['currency']} ({change:+.1f}%)")
        total = totals.setdefault(item["currency"], [0.0, 0.0])
        total[0] += value
        total[1] += cost
    summary = ", ".join(f"{markets._fmt(v)} {c} ({(v / cost - 1) * 100 if cost else 0:+.1f}%)" for c, (v, cost) in totals.items())
    return "Портфейл — " + "; ".join(rows) + f". Общо: {summary}."


@jarvis_tool
def portfolio_remove(asset: str) -> str:
    """Маха актив от портфейла.

    Args:
        asset: Активът.
    """
    symbol = markets.resolve(asset)
    items = alerts.load(alerts.PORTFOLIO)
    kept = [i for i in items if i["symbol"] != symbol]
    alerts.save(alerts.PORTFOLIO, kept)
    return f"Махнах {len(items) - len(kept)} записа от портфейла."
