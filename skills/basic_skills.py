"""
Основни умения на JARVIS.

Всеки .py файл в папка `skills/` се зарежда автоматично при старт.
За ново умение: напишете функция с type hints и docstring и сложете @jarvis_tool.
"""
import ast
import json
import math
import operator
import re
import urllib.parse
import urllib.request
from datetime import date, datetime

from jarvis import apps, clock, jarvis_tool, when


@jarvis_tool
def get_current_time(city: str = "") -> str:
    """Часовник и календар: точният час, датата и денят от седмицата — тук или в друг град по света.
    Не е за метеорологичното време.

    Args:
        city: Град или държава, напр. "Токио". Празно — тук, при сър.
    """
    if not city.strip():
        now = datetime.now()
        return f"Днес е {clock.date_text(now)}, часът е {clock.time_text(now)}."
    zone = clock.zone_for(city)
    if not zone:
        raise ValueError(f"не знам часовата зона на „{city}“")
    here, there = datetime.now().astimezone(), datetime.now(zone)
    hours = round((there.utcoffset() - here.utcoffset()).total_seconds() / 3600, 1)
    difference = "същото време като тук" if hours == 0 else (
        f"{abs(hours):g} {'час' if abs(hours) == 1 else 'часа'} {'напред' if hours > 0 else 'назад'} спрямо тук")
    return f"{clock.in_place(city, capital=True)} е {clock.date_text(there)}, часът е {clock.time_text(there)} ({difference})."


# --- Безопасен калкулатор (без eval!) ---------------------------------------------
_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _evaluate(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        # 9**9**9 би смятало часове и би блокирало JARVIS — ограничаваме до ~3000 цифри.
        if (isinstance(node.op, ast.Pow) and isinstance(left, int) and isinstance(right, int)
                and abs(left) > 1 and right > 0 and right * math.log2(abs(left)) > 10_000):
            raise ValueError("резултатът е твърде голям за изчисляване")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("позволени са само числа и + - * / // % **")


@jarvis_tool
def calculate(expression: str) -> str:
    """Изчислява математически израз точно. Използвай винаги за сметки.

    Args:
        expression: Математически израз, напр. "(12.5 * 4) / 3 + 2**10".
    """
    result = _evaluate(ast.parse(expression, mode="eval").body)
    return f"{expression} = {round(result, 10)}"


# --- Програми и сайтове (търсенето е в jarvis/apps.py) -------------------------------
# Стартират се само инсталирани програми и само http(s) адреси — моделът не може да
# изпълни произволна команда. Свои имена добавяте в PROGRAMS и SITES в jarvis/apps.py.
@jarvis_tool
def open_program(name: str) -> str:
    """Стартира инсталирана програма или игра — Chrome, калкулатор, бележник, Steam, Discord, Word и др.

    Args:
        name: Името на програмата, както го е казал сър, напр. "chrome", "калкулатор", "Steam".
    """
    return apps.open_program(name)


@jarvis_tool
def open_website(url: str) -> str:
    """Отваря уебсайт в браузъра — YouTube, Google, Facebook, abv.bg и др.

    Args:
        url: Адрес или име на сайта, напр. "youtube.com" или "ютуб".
    """
    if not apps.find_site(url):
        # Моделът понякога праща програма като сайт („chrome://newtab“ вместо Chrome).
        program = url.split("://")[0]
        if apps.find_program(program, fuzzy=False):
            return apps.open_program(program)
    return apps.open_site(url)


# wttr.in понякога връща описанието само на английски. Редът е важен: по-точното първо.
_WEATHER_BG = [
    ("thunder", "гръмотевици"), ("blizzard", "виелица"), ("sleet", "суграшица"), ("snow", "сняг"),
    ("torrential", "проливен дъжд"), ("heavy rain", "силен дъжд"), ("moderate rain", "умерен дъжд"),
    ("light rain", "слаб дъжд"), ("drizzle", "ръмеж"), ("rain", "превалявания"), ("shower", "превалявания"),
    ("freezing fog", "ледена мъгла"), ("fog", "мъгла"), ("mist", "мъгла"), ("overcast", "облачно"),
    ("partly", "разкъсана облачност"), ("cloudy", "облачно"), ("sunny", "слънчево"), ("clear", "ясно"),
]


_CYRILLIC = [("sht", "щ"), ("dzh", "дж"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("ts", "ц"),
             ("yu", "ю"), ("ya", "я"), ("ia", "ия"), *zip("abvgdeziyklmnoprstufhcwj", "абвгдезийклмнопрстуфхквй")]


def _to_cyrillic(name: str) -> str:
    """Български град на латиница -> кирилица: „Veliko Tarnovo“ -> „Велико Тарново“."""
    words = []
    for word in name.lower().split():
        i, out = 0, ""
        while i < len(word):
            latin, cyrillic = next(((l, c) for l, c in _CYRILLIC if word.startswith(l, i)), (word[i], word[i]))
            out, i = out + cyrillic, i + len(latin)
        words.append(out.capitalize())
    return " ".join(words)


def _weather_in_bulgarian(description: str) -> str:
    if re.search(r"[а-яА-Я]", description):
        return description
    lowered = description.lower()
    return next((bg for en, bg in _WEATHER_BG if en in lowered), description)


def _forecast(city: str, days: list[dict], day: str) -> str:
    """Прогнозата на wttr.in за един от следващите три дни."""
    target = when.parse_date(day) or date.today()
    forecast = next((d for d in days if d["date"] == target.isoformat()), None)
    if not forecast:
        last = re.sub(r"^във? ", "", when.spoken_date(date.fromisoformat(days[-1]["date"])))
        return f"Имам прогноза само до {last}."
    hours = forecast["hourly"]
    midday = hours[len(hours) // 2]
    description = _weather_in_bulgarian((midday.get("lang_bg") or midday["weatherDesc"])[0]["value"].strip())
    rain = max(int(h.get("chanceofrain", 0)) for h in hours)
    return (f"{city}, {when.spoken_date(target)}: от {forecast['mintempC']} до {forecast['maxtempC']}°C, "
            f"{description}, вероятност за дъжд до {rain}%.")


@jarvis_tool
def get_weather(city: str = "", day: str = "") -> str:
    """Метеорологичното време — сега или прогноза за днес, утре и вдругиден: температура, облаци, дъжд,
    вятър. За „какво е времето“, „студено ли е“, „ще вали ли утре“.

    Args:
        city: Град, напр. "София". Празно — мястото, където се намира сър.
        day: Празно — времето сега. Или ден за прогнозата: "днес", "утре", "вдругиден", "в събота".
    """
    url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1&lang=bg"
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.load(response)
    current = data["current_condition"][0]
    description = _weather_in_bulgarian((current.get("lang_bg") or current["weatherDesc"])[0]["value"].strip())
    if not city:
        area = data.get("nearest_area", [{}])[0]
        city = area.get("areaName", [{}])[0].get("value", "Навън")
        if area.get("country", [{}])[0].get("value") == "Bulgaria":
            city = _to_cyrillic(city)  # „Sofia“ -> „София“
    if day.strip():
        return _forecast(city, data["weather"], day)
    return (
        f"{city}: {current['temp_C']}°C (усеща се като {current['FeelsLikeC']}°C), {description}, "
        f"вятър {current['windspeedKmph']} км/ч, влажност {current['humidity']}%."
    )
