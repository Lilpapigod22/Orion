"""
Още за времето (Open-Meteo): прогноза за седмицата, по часове, кога ще вали, качеството на
въздуха и UV индексът.
"""
from datetime import date, datetime

from jarvis import geo, jarvis_tool, when


def _code(value: int) -> str:
    return geo.WEATHER_CODES.get(value, "променливо")


@jarvis_tool
def weather_week(city: str = "") -> str:
    """Прогнозата за 7 дни напред — ден по ден: температура, валежи, вятър.

    Args:
        city: Град (празно — там, където е сър).
    """
    place = geo.place(city)
    d = geo.forecast(place, 7)["daily"]
    days = []
    for i, day in enumerate(d["time"]):
        spoken = when.spoken_date(date.fromisoformat(day))
        days.append(f"{spoken}: {d['temperature_2m_min'][i]:.0f}–{d['temperature_2m_max'][i]:.0f}°, "
                    f"{_code(d['weather_code'][i])}, дъжд {d['precipitation_probability_max'][i] or 0}%")
    return f"{place.name}, 7 дни: " + "; ".join(days) + "."


@jarvis_tool
def weather_hourly(city: str = "", hours: int = 12) -> str:
    """Прогнозата по часове за следващите часове — температура и вероятност за дъжд.

    Args:
        city: Град (празно — там, където е сър).
        hours: За колко часа напред (по подразбиране 12).
    """
    place = geo.place(city)
    h = geo.forecast(place, 2)["hourly"]
    now = datetime.now().strftime("%Y-%m-%dT%H:00")
    start = next((i for i, t in enumerate(h["time"]) if t >= now), 0)
    rows = [f"{h['time'][i][11:16]} {h['temperature_2m'][i]:.0f}° {_code(h['weather_code'][i])}"
            + (f" ({h['precipitation_probability'][i]}% дъжд)" if (h['precipitation_probability'][i] or 0) >= 30 else "")
            for i in range(start, min(start + max(1, min(hours, 24)), len(h["time"])), 2)]
    return f"{place.name}, следващите {hours} часа: " + "; ".join(rows) + "."


@jarvis_tool
def will_it_rain(city: str = "", day: str = "днес") -> str:
    """Ще вали ли и в колко часа — днес, утре или друг ден (до 7 дни). За „трябва ли ми чадър“.

    Args:
        city: Град (празно — там, където е сър).
        day: Кой ден: "днес", "утре", "в събота"…
    """
    place = geo.place(city)
    target = (when.parse_date(day) or date.today()).isoformat()
    h = geo.forecast(place, 7)["hourly"]
    wet = [h["time"][i][11:16] for i, t in enumerate(h["time"])
           if t.startswith(target) and ((h["precipitation_probability"][i] or 0) >= 50 or (h["precipitation"][i] or 0) >= 0.3)]
    spoken = when.spoken_date(date.fromisoformat(target))
    if not wet:
        return f"{place.name}, {spoken}: не се очаква дъжд — чадърът не е нужен."
    return f"{place.name}, {spoken}: вероятен дъжд около {wet[0]}" + (f" до {wet[-1]}" if len(wet) > 1 else "") + " — вземете чадър."


@jarvis_tool
def air_quality(city: str = "") -> str:
    """Качеството на въздуха сега: индекс, фини прахови частици (ФПЧ 2.5 и 10), озон.

    Args:
        city: Град (празно — там, където е сър).
    """
    place = geo.place(city)
    a = geo.air(place)
    aqi = a["european_aqi"]
    label = ("добро" if aqi <= 20 else "задоволително" if aqi <= 40 else "умерено" if aqi <= 60
             else "лошо" if aqi <= 80 else "много лошо" if aqi <= 100 else "изключително лошо")
    return (f"{place.name}: въздухът е {label} (европейски индекс {aqi}). ФПЧ 2.5: {a['pm2_5']:.0f} µg/m³, "
            f"ФПЧ 10: {a['pm10']:.0f}, озон: {a['ozone']:.0f}.")


@jarvis_tool
def uv_index(city: str = "") -> str:
    """UV индексът днес и нужен ли е слънцезащитен крем.

    Args:
        city: Град (празно — там, където е сър).
    """
    place = geo.place(city)
    uv = geo.forecast(place, 1)["daily"]["uv_index_max"][0] or 0
    advice = ("нисък — не е нужна защита" if uv < 3 else "умерен — крем при дълъг престой" if uv < 6
              else "висок — крем, шапка и сянка по обед" if uv < 8 else "много висок — избягвайте слънцето по обед")
    return f"{place.name}: UV индексът днес достига {uv:.0f} — {advice}."
