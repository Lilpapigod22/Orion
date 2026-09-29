"""
Знания и превръщания: Уикипедия, валути, мерни единици, песни и клипове в YouTube.
"""
import json
import re
import urllib.parse
import urllib.request
import webbrowser

from jarvis import jarvis_tool

USER_AGENT = "Mitko/1.0 (personal voice assistant)"  # само латиница: HTTP заглавията не приемат кирилица


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)


# --- Уикипедия ----------------------------------------------------------------------------------
@jarvis_tool
def wikipedia(topic: str) -> str:
    """Кратка справка от Уикипедия — хора, места, събития, понятия. Първо на български, после на английски.

    Args:
        topic: За какво, напр. "Иван Вазов" или "черна дупка".
    """
    latin = not re.search(r"[а-яА-Я]", topic)
    for lang in ("en", "bg") if latin else ("bg", "en"):
        base = f"https://{lang}.wikipedia.org"
        query = urllib.parse.quote(topic)
        # Първо по заглавие („Иван Вазов“), после в целия текст — иначе печелят случайни статии.
        titles = _get_json(f"{base}/w/api.php?action=opensearch&limit=1&namespace=0&format=json&search={query}")[1]
        if not titles:
            found = _get_json(f"{base}/w/api.php?action=query&list=search&format=json&srlimit=1&srsearch={query}")
            titles = [hit["title"] for hit in found.get("query", {}).get("search", [])]
        if not titles:
            continue
        title = titles[0]
        page = _get_json(f"{base}/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_")))
        extract = (page.get("extract") or "").strip()
        if extract:
            source = "Уикипедия" if lang == "bg" else "английската Уикипедия (преведи на български)"
            return f"{title} ({source}): {extract[:1500]}"
    return f"Не намерих статия за „{topic}“ в Уикипедия."


# --- Валути -------------------------------------------------------------------------------------
_CURRENCIES = {
    "лев": "BGN", "лева": "BGN", "bgn": "BGN", "евро": "EUR", "eur": "EUR", "€": "EUR",
    "долар": "USD", "долара": "USD", "долари": "USD", "usd": "USD", "$": "USD",
    "паунд": "GBP", "паунда": "GBP", "лира": "GBP", "лири": "GBP", "британски": "GBP", "gbp": "GBP", "£": "GBP",
    "франк": "CHF", "франка": "CHF", "chf": "CHF", "турски": "TRY", "try": "TRY",
    "леи": "RON", "лея": "RON", "румънски": "RON", "ron": "RON", "йена": "JPY", "йени": "JPY", "jpy": "JPY",
    "юан": "CNY", "юана": "CNY", "cny": "CNY", "злоти": "PLN", "pln": "PLN", "крона": "SEK", "sek": "SEK",
    "канадски": "CAD", "cad": "CAD", "австралийски": "AUD", "aud": "AUD", "динар": "RSD", "динара": "RSD",
}
BGN_PER_EUR = 1.95583  # фиксиран курс — левът вече не се котира отделно


def _currency(text: str) -> str:
    words = re.findall(r"[\w€$£]+", text.lower())
    for word in words:
        if word in _CURRENCIES:
            return _CURRENCIES[word]
    code = text.strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code):
        return code
    raise ValueError(f"не познавам валутата „{text}“")


def _rate(src: str, dst: str) -> float:
    """Колко `dst` струва 1 `src` (курсове на ЕЦБ; левът — през еврото)."""
    if src == dst:
        return 1.0
    if src == "BGN":
        return _rate("EUR", dst) / BGN_PER_EUR
    if dst == "BGN":
        return _rate(src, "EUR") * BGN_PER_EUR
    data = _get_json(f"https://api.frankfurter.dev/v1/latest?base={src}&symbols={dst}")
    if dst not in data.get("rates", {}):
        raise ValueError(f"нямам курс {src} → {dst}")
    return data["rates"][dst]


@jarvis_tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Превръща пари от една валута в друга по днешния курс (евро, долар, лев, паунд, франк…).

    Args:
        amount: Сумата, напр. 100.
        from_currency: От коя валута, напр. "долар" или "USD".
        to_currency: В коя валута, напр. "евро" или "EUR".
    """
    src, dst = _currency(from_currency), _currency(to_currency)
    rate = _rate(src, dst)
    return f"{amount:g} {src} = {amount * rate:,.2f} {dst} (курс 1 {src} = {rate:.4f} {dst})".replace(",", " ")


# --- Мерни единици ------------------------------------------------------------------------------
# Всяка единица -> (вид, колко основни единици е). Основни: метър, килограм, литър, м/с, м², секунда.
_UNITS = {
    **dict.fromkeys(["мм", "милиметър", "милиметра", "mm"], ("length", 0.001)),
    **dict.fromkeys(["см", "сантиметър", "сантиметра", "cm"], ("length", 0.01)),
    **dict.fromkeys(["м", "метър", "метра", "m"], ("length", 1.0)),
    **dict.fromkeys(["км", "километър", "километра", "km"], ("length", 1000.0)),
    **dict.fromkeys(["инч", "инча", "in", "inch"], ("length", 0.0254)),
    **dict.fromkeys(["фут", "фута", "ft", "feet"], ("length", 0.3048)),
    **dict.fromkeys(["ярд", "ярда", "yd"], ("length", 0.9144)),
    **dict.fromkeys(["миля", "мили", "mile", "miles", "mi"], ("length", 1609.344)),
    **dict.fromkeys(["морска миля", "морски мили"], ("length", 1852.0)),
    **dict.fromkeys(["г", "грам", "грама", "g"], ("mass", 0.001)),
    **dict.fromkeys(["кг", "килограм", "килограма", "kg"], ("mass", 1.0)),
    **dict.fromkeys(["т", "тон", "тона", "t"], ("mass", 1000.0)),
    **dict.fromkeys(["унция", "унции", "oz"], ("mass", 0.028349523)),
    **dict.fromkeys(["паунд", "паунда", "фунт", "фунта", "lb", "lbs"], ("mass", 0.45359237)),
    **dict.fromkeys(["мл", "милилитър", "милилитра", "ml"], ("volume", 0.001)),
    **dict.fromkeys(["л", "литър", "литра", "l"], ("volume", 1.0)),
    **dict.fromkeys(["галон", "галона", "gal"], ("volume", 3.785411784)),
    **dict.fromkeys(["чаша", "чаши", "cup"], ("volume", 0.24)),
    **dict.fromkeys(["км/ч", "километра в час", "kmh", "km/h"], ("speed", 1 / 3.6)),
    **dict.fromkeys(["м/с", "метра в секунда", "m/s"], ("speed", 1.0)),
    **dict.fromkeys(["мили в час", "mph"], ("speed", 0.44704)),
    **dict.fromkeys(["възел", "възела"], ("speed", 0.514444)),
    **dict.fromkeys(["м2", "кв. м", "квадратен метър", "квадратни метра"], ("area", 1.0)),
    **dict.fromkeys(["декар", "декара"], ("area", 1000.0)),
    **dict.fromkeys(["хектар", "хектара", "ha"], ("area", 10000.0)),
    **dict.fromkeys(["акър", "акра"], ("area", 4046.8564224)),
    **dict.fromkeys(["км2", "квадратен километър", "квадратни километра"], ("area", 1e6)),
    **dict.fromkeys(["секунда", "секунди", "s"], ("time", 1.0)),
    **dict.fromkeys(["минута", "минути", "min"], ("time", 60.0)),
    **dict.fromkeys(["час", "часа", "h"], ("time", 3600.0)),
    **dict.fromkeys(["ден", "дни", "дена"], ("time", 86400.0)),
    **dict.fromkeys(["седмица", "седмици"], ("time", 604800.0)),
    **dict.fromkeys(["година", "години"], ("time", 31557600.0)),
}
_TEMPERATURE = {"c": "C", "°c": "C", "целзий": "C", "целзиеви": "C", "градуса": "C", "f": "F", "°f": "F",
                "фаренхайт": "F", "k": "K", "келвин": "K", "келвина": "K"}


def _unit(text: str):
    t = text.lower().strip().rstrip(".")
    if t in _UNITS:
        return _UNITS[t]
    for name in sorted(_UNITS, key=len, reverse=True):  # „квадратни метра“ преди „метра“
        if len(name) > 2 and name in t:
            return _UNITS[name]
    raise ValueError(f"не познавам мерната единица „{text}“")


@jarvis_tool
def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Превръща мерни единици: дължина (км, мили, инчове), тегло (кг, паунди), обем (литри, галони),
    скорост, площ (декари, акри), време и температура (°C, °F).

    Args:
        value: Числото, напр. 10.
        from_unit: От каква единица, напр. "мили" или "°F".
        to_unit: В каква единица, напр. "км" или "°C".
    """
    src_t = _TEMPERATURE.get(from_unit.lower().strip())
    dst_t = _TEMPERATURE.get(to_unit.lower().strip())
    if src_t and dst_t:
        celsius = {"C": value, "F": (value - 32) * 5 / 9, "K": value - 273.15}[src_t]
        result = {"C": celsius, "F": celsius * 9 / 5 + 32, "K": celsius + 273.15}[dst_t]
        return f"{value:g} °{src_t} = {result:.1f} °{dst_t}".replace("°K", "K")
    (kind_a, factor_a), (kind_b, factor_b) = _unit(from_unit), _unit(to_unit)
    if kind_a != kind_b:
        raise ValueError(f"„{from_unit}“ и „{to_unit}“ не са от един вид")
    result = value * factor_a / factor_b
    shown = f"{result:.4g}" if abs(result) < 1e6 else f"{result:,.0f}".replace(",", " ")
    return f"{value:g} {from_unit} = {shown} {to_unit}"


# --- Музика и клипове ------------------------------------------------------------------------------
@jarvis_tool
def play_on_youtube(query: str) -> str:
    """Пуска песен или клип в YouTube — направо видеото, не търсенето. За „пусни ми песента…“.

    Args:
        query: Песен, изпълнител или клип, напр. "Мадона Frozen".
    """
    from ddgs import DDGS
    with DDGS() as ddgs:
        videos = ddgs.videos(query, max_results=6)
    youtube = [v for v in videos if "youtube.com/watch" in (v.get("content") or "")]
    if not youtube:
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query))
        return f"Не намерих точното видео — отворих търсенето за „{query}“ в YouTube."
    # Официалното видео, ако го има.
    best = next((v for v in youtube if "official" in v.get("title", "").lower()), youtube[0])
    webbrowser.open(best["content"])
    return f"Пуснах „{best['title']}“ в YouTube."
