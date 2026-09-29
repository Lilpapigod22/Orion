"""
Места: информация за държави, разстояния между градове, маршрут и „какво има наблизо“ в Google Maps.
"""
import re
import urllib.parse
import webbrowser

from jarvis import geo, jarvis_tool


@jarvis_tool
def country_info(country: str) -> str:
    """Справка за държава: столица, население, площ, валута, езици, регион.

    Args:
        country: Държавата, напр. "Япония" или "Germany".
    """
    # Wikidata: първо бързото търсене на идентификатора, после данните — с български имена.
    lang = "en" if re.fullmatch(r"[A-Za-z .'-]+", country.strip()) else "bg"
    found = geo.get_json("https://www.wikidata.org/w/api.php?action=wbsearchentities&type=item&format=json&limit=5"
                         f"&language={lang}&uselang=bg&search=" + urllib.parse.quote(country.strip()))["search"]
    if not found:
        raise ValueError(f"не намирам държава „{country}“")
    ids = " ".join(f"wd:{f['id']}" for f in found)
    sparql = f"""SELECT ?country ?countryLabel ?capitalLabel ?population ?area ?currencyLabel ?languageLabel ?continentLabel
      WHERE {{ VALUES ?country {{ {ids} }} ?country wdt:P31/wdt:P279* wd:Q6256.
      OPTIONAL {{ ?country wdt:P36 ?capital. }} OPTIONAL {{ ?country wdt:P1082 ?population. }}
      OPTIONAL {{ ?country wdt:P2046 ?area. }} OPTIONAL {{ ?country wdt:P38 ?currency. }}
      OPTIONAL {{ ?country wdt:P37 ?language. }} OPTIONAL {{ ?country wdt:P30 ?continent. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "bg,en". }} }}"""
    rows = geo.get_json("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(sparql))
    rows = rows["results"]["bindings"]
    if not rows:
        raise ValueError(f"„{country}“ не е държава")
    first_id = next(f["id"] for f in found if any(r["country"]["value"].endswith(f["id"]) for r in rows))
    rows = [r for r in rows if r["country"]["value"].endswith(first_id)]

    def values(key: str) -> list[str]:
        return list(dict.fromkeys(r[key]["value"] for r in rows if key in r))

    def number(key: str) -> str:
        value = max((float(v) for v in values(key)), default=0)
        return f"{value:,.0f}".replace(",", " ")

    return (f"{rows[0]['countryLabel']['value']}: столица {', '.join(values('capitalLabel')[:2]) or '—'}, "
            f"население {number('population')} души, площ {number('area')} км², "
            f"валута {', '.join(values('currencyLabel')[:2]) or '—'}, "
            f"официален език {', '.join(values('languageLabel')[:3]) or '—'}, "
            f"континент {', '.join(values('continentLabel')[:2]) or '—'}.")


@jarvis_tool
def distance_between(from_city: str, to_city: str = "") -> str:
    """Използвай това умение, когато питаш за разстоянието между два града или локация и приблизително
    времето за пътуване с кола. Примери: „Колко километра е от София до Бургас?“, „Сколько време ще
    ми отнеме да стигна до Варна?/" и „Какво е разстоянието между Пловдив и Стара Загора?/".

    Args:
        from_city: Първият град.
        to_city: Вторият град (празно — от там, където е сър).
    """
    a = geo.find(from_city)
    b = geo.find(to_city) if to_city.strip() else geo.here()
    km = geo.distance_km(a, b)
    road = km * 1.25  # пътищата не са прави
    hours = road / 75
    return (f"От {a.name} до {b.name}: около {km:.0f} км по права линия, с кола приблизително {road:.0f} км "
            f"и {int(hours)} ч. {int(hours % 1 * 60)} мин.")


@jarvis_tool
def open_directions(destination: str, origin: str = "") -> str:
    """Отваря маршрут в Google Maps — как да стигна до някъде.

    Args:
        destination: Накъде, напр. "летище София" или "Пловдив".
        origin: Откъде (празно — от текущото място).
    """
    params = {"api": "1", "destination": destination}
    if origin.strip():
        params["origin"] = origin
    webbrowser.open("https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params))
    return f"Отворих маршрута до {destination} в Google Maps."


@jarvis_tool
def find_nearby(what: str) -> str:
    """Търси наблизо в Google Maps: аптека, бензиностанция, ресторант, банкомат, болница…

    Args:
        what: Какво, напр. "аптека" или "пица".
    """
    webbrowser.open("https://www.google.com/maps/search/" + urllib.parse.quote(f"{what} наблизо"))
    return f"Отворих „{what} наблизо“ в Google Maps."


@jarvis_tool
def open_map(place: str) -> str:
    """Показва място на картата (Google Maps).

    Args:
        place: Мястото или адресът.
    """
    webbrowser.open("https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(place))
    return f"Показах {place} на картата."
