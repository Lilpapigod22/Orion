"""Date and time in Bulgarian — one place for the brain, the reflexes and the get_current_time skill."""
from datetime import datetime

WEEKDAYS = ("понеделник", "вторник", "сряда", "четвъртък", "петък", "събота", "неделя")
MONTHS = ("януари", "февруари", "март", "април", "май", "юни", "юли", "август",
          "септември", "октомври", "ноември", "декември")


def weekday(now: datetime | None = None) -> str:
    """„петък“"""
    return WEEKDAYS[(now or datetime.now()).weekday()]


def date_text(now: datetime | None = None) -> str:
    """„петък, 25 септември 2026 г.“"""
    now = now or datetime.now()
    return f"{WEEKDAYS[now.weekday()]}, {now.day} {MONTHS[now.month - 1]} {now.year} г."


def time_text(now: datetime | None = None) -> str:
    """„10:30“"""
    return f"{now or datetime.now():%H:%M}"


def in_place(name: str, capital: bool = False) -> str:
    """„във Варна“, „в Токио“ — „във“ before „в“ and „ф“. With `capital` — „Във Варна“ at the start of a sentence."""
    name = name.strip()
    preposition = "във" if name[:1].lower() in "вфvf" else "в"
    return f"{preposition.capitalize() if capital else preposition} {name}"


# City or country -> time zone. Unknown ones are also looked up in the full zone list by English name.
CITY_ZONES = {
    **dict.fromkeys(["токио", "tokyo", "япония"], "Asia/Tokyo"),
    **dict.fromkeys(["ню йорк", "new york", "вашингтон", "washington", "маями", "miami", "бостън", "boston",
                     "сащ", "америка"], "America/New_York"),
    **dict.fromkeys(["лос анджелис", "los angeles", "сан франциско", "san francisco", "лас вегас",
                     "las vegas", "сиатъл", "seattle", "калифорния"], "America/Los_Angeles"),
    **dict.fromkeys(["чикаго", "chicago", "тексас", "далас", "dallas", "хюстън", "houston"], "America/Chicago"),
    **dict.fromkeys(["торонто", "toronto", "монреал", "канада"], "America/Toronto"),
    **dict.fromkeys(["ванкувър", "vancouver"], "America/Vancouver"),
    **dict.fromkeys(["мексико", "mexico city"], "America/Mexico_City"),
    **dict.fromkeys(["сао пауло", "são paulo", "рио", "рио де жанейро", "бразилия"], "America/Sao_Paulo"),
    **dict.fromkeys(["буенос айрес", "аржентина"], "America/Argentina/Buenos_Aires"),
    **dict.fromkeys(["хонолулу", "хавай", "хаваи"], "Pacific/Honolulu"),
    **dict.fromkeys(["лондон", "london", "англия", "великобритания"], "Europe/London"),
    **dict.fromkeys(["дъблин", "ирландия"], "Europe/Dublin"),
    **dict.fromkeys(["лисабон", "португалия"], "Europe/Lisbon"),
    **dict.fromkeys(["париж", "paris", "франция"], "Europe/Paris"),
    **dict.fromkeys(["берлин", "berlin", "германия", "мюнхен"], "Europe/Berlin"),
    **dict.fromkeys(["мадрид", "испания", "барселона"], "Europe/Madrid"),
    **dict.fromkeys(["рим", "италия", "милано"], "Europe/Rome"),
    **dict.fromkeys(["виена", "австрия"], "Europe/Vienna"),
    **dict.fromkeys(["амстердам", "холандия", "нидерландия"], "Europe/Amsterdam"),
    **dict.fromkeys(["брюксел", "белгия"], "Europe/Brussels"),
    **dict.fromkeys(["цюрих", "женева", "швейцария"], "Europe/Zurich"),
    **dict.fromkeys(["прага", "чехия"], "Europe/Prague"),
    **dict.fromkeys(["варшава", "полша"], "Europe/Warsaw"),
    **dict.fromkeys(["будапеща", "унгария"], "Europe/Budapest"),
    **dict.fromkeys(["стокхолм", "швеция"], "Europe/Stockholm"),
    **dict.fromkeys(["осло", "норвегия"], "Europe/Oslo"),
    **dict.fromkeys(["копенхаген", "дания"], "Europe/Copenhagen"),
    **dict.fromkeys(["хелзинки", "финландия"], "Europe/Helsinki"),
    **dict.fromkeys(["атина", "гърция", "солун"], "Europe/Athens"),
    **dict.fromkeys(["букурещ", "румъния"], "Europe/Bucharest"),
    **dict.fromkeys(["белград", "сърбия"], "Europe/Belgrade"),
    **dict.fromkeys(["скопие", "македония", "северна македония"], "Europe/Skopje"),
    **dict.fromkeys(["истанбул", "турция", "анкара"], "Europe/Istanbul"),
    **dict.fromkeys(["киев", "украйна"], "Europe/Kyiv"),
    **dict.fromkeys(["москва", "русия", "санкт петербург"], "Europe/Moscow"),
    **dict.fromkeys(["дубай", "обединени арабски емирства", "абу даби"], "Asia/Dubai"),
    **dict.fromkeys(["ню делхи", "делхи", "мумбай", "индия"], "Asia/Kolkata"),
    **dict.fromkeys(["бангкок", "тайланд"], "Asia/Bangkok"),
    **dict.fromkeys(["сингапур"], "Asia/Singapore"),
    **dict.fromkeys(["хонконг"], "Asia/Hong_Kong"),
    **dict.fromkeys(["пекин", "шанхай", "китай"], "Asia/Shanghai"),
    **dict.fromkeys(["сеул", "корея", "южна корея"], "Asia/Seoul"),
    **dict.fromkeys(["сидни", "мелбърн", "канбера", "австралия"], "Australia/Sydney"),
    **dict.fromkeys(["окланд", "нова зеландия"], "Pacific/Auckland"),
    **dict.fromkeys(["кайро", "египет"], "Africa/Cairo"),
    **dict.fromkeys(["йоханесбург", "южна африка"], "Africa/Johannesburg"),
    **dict.fromkeys(["софия", "българия", "пловдив", "варна", "бургас"], "Europe/Sofia"),
}


def zone_for(place: str):
    """The time zone (ZoneInfo) of a city or country, or None."""
    from zoneinfo import ZoneInfo, available_timezones
    name = place.lower().strip().removeprefix("в ").removeprefix("във ").strip()
    if name in CITY_ZONES:
        return ZoneInfo(CITY_ZONES[name])
    wanted = name.replace(" ", "_")
    for zone in available_timezones():
        if zone.lower().rsplit("/", 1)[-1] == wanted:
            return ZoneInfo(zone)
    return None
