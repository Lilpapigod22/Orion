"""
Места и прогноза: градове по име (Open-Meteo), къде е сър (по IP), разстояния, прогнозата
по часове и дни, качеството на въздуха. Всичко е безплатно и без регистрация.
"""
import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

USER_AGENT = "Orion/1.0 (personal voice assistant)"

# Код на времето (WMO) -> описание.
WEATHER_CODES = {
    0: "ясно", 1: "предимно ясно", 2: "разкъсана облачност", 3: "облачно", 45: "мъгла", 48: "мъгла със скреж",
    51: "слаб ръмеж", 53: "ръмеж", 55: "силен ръмеж", 56: "леден ръмеж", 57: "леден ръмеж",
    61: "слаб дъжд", 63: "дъжд", 65: "силен дъжд", 66: "леден дъжд", 67: "силен леден дъжд",
    71: "слаб сняг", 73: "сняг", 75: "силен сняг", 77: "снежни зърна", 80: "превалявания",
    81: "превалявания", 82: "силни превалявания", 85: "снеговалежи", 86: "силни снеговалежи",
    95: "гръмотевична буря", 96: "буря с градушка", 99: "силна буря с градушка",
}


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    country: str = ""
    population: int = 0


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


@lru_cache(maxsize=64)
def find(name: str) -> Place:
    """Град или място по име („Варна“, „Paris“)."""
    data = get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=bg&format=json&name="
                    + urllib.parse.quote(name.strip()))
    results = data.get("results") or []
    if not results:
        raise ValueError(f"не намирам място „{name}“")
    r = results[0]
    return Place(r["name"], r["latitude"], r["longitude"], r.get("country", ""), r.get("population") or 0)


@lru_cache(maxsize=1)
def here() -> Place:
    """Къде е сър — по IP адреса (с точност до града). Ако няма връзка — София."""
    try:
        data = get_json("http://ip-api.com/json/?lang=ru&fields=status,city,country,lat,lon")
        if data.get("status") == "success":
            return Place(data.get("city") or "Тук", data["lat"], data["lon"], data.get("country", ""))
    except OSError:
        pass
    return Place("София", 42.6977, 23.3219, "България")


def place(name: str = "") -> Place:
    return find(name) if name.strip() else here()


def distance_km(a: Place, b: Place) -> float:
    """Разстояние по права линия (формула на хаверсинус)."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def forecast(p: Place, days: int = 7) -> dict:
    daily = ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,"
             "sunrise,sunset,uv_index_max,wind_speed_10m_max,daylight_duration")
    hourly = "temperature_2m,precipitation_probability,precipitation,weather_code"
    return get_json(f"https://api.open-meteo.com/v1/forecast?latitude={p.lat}&longitude={p.lon}"
                    f"&daily={daily}&hourly={hourly}&timezone=auto&forecast_days={days}")


def air(p: Place) -> dict:
    return get_json(f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={p.lat}&longitude={p.lon}"
                    "&current=european_aqi,pm10,pm2_5,ozone,nitrogen_dioxide&timezone=auto")["current"]
