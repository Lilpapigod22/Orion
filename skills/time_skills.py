"""
Дати и време: дата след N дни, дни между дати, ден от седмицата, възраст, изгрев и залез,
фаза на Луната, българските празници и имени дни, хронометър, помодоро, повтарящи се напомняния.
"""
import math
import time
from datetime import date, datetime, timedelta

from jarvis import clock, geo, jarvis_tool, when
from jarvis.reminders import book


def _day(text: str) -> date:
    d = when.parse_date(text) if text.strip() else date.today()
    if not d:
        raise ValueError(f"не разбирам датата „{text}“ — кажете напр. „25.12.2026“ или „25 декември“")
    return d


def _full(d: date) -> str:
    return clock.date_text(datetime.combine(d, datetime.min.time()))


def _days(n: int) -> str:
    return "1 ден" if n == 1 else f"{n} дни"


@jarvis_tool
def date_after_days(days: int, from_date: str = "") -> str:
    """Коя дата ще е след (или беше преди) N дни. За „коя дата е след 100 дни“.

    Args:
        days: Колко дни — отрицателно за „преди“.
        from_date: От коя дата (празно — днес).
    """
    start = _day(from_date)
    return f"{_days(abs(days))} {'след' if days >= 0 else 'преди'} {_full(start)} е {_full(start + timedelta(days=days))}"


@jarvis_tool
def days_between(first_date: str, second_date: str = "") -> str:
    """Колко дни (и седмици) има между две дати.

    Args:
        first_date: Първата дата, напр. "1.1.2026".
        second_date: Втората (празно — днес).
    """
    a, b = _day(first_date), _day(second_date)
    days = abs((b - a).days)
    return (f"Между {_full(min(a, b))} и {_full(max(a, b))} има {_days(days)} "
            f"({days // 7} седмици и {_days(days % 7)}).")


@jarvis_tool
def weekday_of_date(date_text: str) -> str:
    """В кой ден от седмицата е (или беше) дадена дата. За „какъв ден е 25 декември“.

    Args:
        date_text: Датата, напр. "25 декември" или "1.1.2027".
    """
    return _full(_day(date_text)).capitalize()


@jarvis_tool
def age_from_birthday(birthday: str) -> str:
    """На колко години е човек и колко остава до рождения му ден.

    Args:
        birthday: Рождената дата, напр. "15.03.1990".
    """
    born = datetime.strptime(birthday.strip().replace("/", "."), "%d.%m.%Y").date()
    today = date.today()
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    next_bday = born.replace(year=today.year)
    if next_bday < today:
        next_bday = born.replace(year=today.year + 1)
    left = (next_bday - today).days
    return (f"{years} години. Следващият рожден ден е {when.spoken_date(next_bday)} — "
            + ("днес е! Честит рожден ден." if left == 0 else f"след {_days(left)}."))


@jarvis_tool
def sunrise_sunset(city: str = "") -> str:
    """Използвай това умение, за да научиш точния час на изгрев и залез на слънцето както и
    продължението на деня днес или в избран дата. Примерни молби: „В колко часа залязва слънцето
    днес?“, „Кога ще изгрее утре?", „Колко е дълъг денят?" и „Какви са часовете на залеза следващата
    седмица?".

    Args:
        city: Град (празно — там, където е сър).
    """
    place = geo.place(city)
    daily = geo.forecast(place, 1)["daily"]
    length = daily["daylight_duration"][0]
    return (f"{place.name}: изгрев {daily['sunrise'][0][11:16]}, залез {daily['sunset'][0][11:16]}, "
            f"денят е {int(length // 3600)} ч. и {int(length % 3600 // 60)} мин.")


@jarvis_tool
def moon_phase(date_text: str = "") -> str:
    """Фазата на Луната (пълнолуние, нова луна…) за днес или за дата."""
    d = _day(date_text)
    synodic = 29.530588853
    reference = datetime(2000, 1, 6, 18, 14)  # новолуние
    age = ((datetime.combine(d, datetime.min.time()) + timedelta(hours=12) - reference).total_seconds()
           / 86400) % synodic
    lit = (1 - math.cos(2 * math.pi * age / synodic)) / 2 * 100
    names = ["новолуние", "растящ сърп", "първа четвърт", "растяща луна", "пълнолуние",
             "намаляваща луна", "последна четвърт", "намаляващ сърп"]
    phase = names[int((age / synodic) * 8 + 0.5) % 8]
    full_in = (synodic / 2 - age) % synodic
    return (f"{_full(d).capitalize()}: {phase}, осветена {lit:.0f}%. "
            f"Следващото пълнолуние е след {_days(round(full_in))} ({when.spoken_date(d + timedelta(days=round(full_in)))}).")


def _holidays(year: int) -> list[dict]:
    return geo.get_json(f"https://date.nager.at/api/v3/PublicHolidays/{year}/BG")


@jarvis_tool
def bulgarian_holidays(year: int = 0) -> str:
    """Официалните почивни дни и празници в България за година.

    Args:
        year: Годината (0 — тази година).
    """
    year = year or date.today().year
    items = _holidays(year)
    return f"Празници през {year}: " + "; ".join(
        f"{date.fromisoformat(h['date']):%d.%m} — {h['localName']}" for h in items) + "."


@jarvis_tool
def next_holiday() -> str:
    """Кой е следващият официален празник (почивен ден) в България и след колко дни."""
    today = date.today()
    items = [h for h in _holidays(today.year) + _holidays(today.year + 1) if date.fromisoformat(h["date"]) >= today]
    h = items[0]
    d = date.fromisoformat(h["date"])
    return f"Следващият празник е {h['localName']} — {when.spoken_date(d)}, след {_days((d - today).days)}."


# Големите имени дни с постоянна дата (подвижните — около Великден — не са тук).
NAME_DAYS = {
    (1, 1): ("Васильовден", "Васил, Василка, Веселин, Веселина"),
    (1, 6): ("Йордановден", "Йордан, Йорданка, Богдан, Богдана, Дана"),
    (1, 7): ("Ивановден", "Иван, Иванка, Йоан, Йоана, Ваня, Жана"),
    (1, 17): ("Антоновден", "Антон, Антония, Антоанета, Андон"),
    (1, 18): ("Атанасовден", "Атанас, Атанаска, Наско, Таня"),
    (2, 14): ("Трифон Зарезан", "Трифон, Трифонка"),
    (3, 25): ("Благовещение", "Благой, Благовеста, Благовест, Евангелина, Вангел"),
    (5, 6): ("Гергьовден", "Георги, Гергана, Галя, Гошо, Генади, Гинка"),
    (5, 11): ("Св. св. Кирил и Методий", "Кирил, Кирилка, Методий"),
    (5, 21): ("Св. св. Константин и Елена", "Константин, Костадин, Елена, Елин, Ленко"),
    (6, 29): ("Петровден", "Петър, Петя, Петра, Павел, Павлина"),
    (7, 20): ("Илинден", "Илия, Илиян, Илияна, Илко"),
    (8, 15): ("Голяма Богородица", "Мария, Марияна, Мариана, Мара, Марио, Мариян"),
    (9, 17): ("Вяра, Надежда и Любов", "Вяра, Надежда, Любов, Люба, Любомир, София"),
    (10, 14): ("Петковден", "Петко, Петкана, Параскева"),
    (10, 26): ("Димитровден", "Димитър, Димитрина, Орион, Мита, Димо, Митра"),
    (11, 8): ("Архангеловден", "Михаил, Михаела, Гаврил, Ангел, Ангелина, Рафаил"),
    (11, 24): ("Екатериновден", "Екатерина, Катя, Катерина"),
    (11, 30): ("Андреевден", "Андрей, Андреа, Андриана"),
    (12, 4): ("Варвара", "Варвара, Варя"),
    (12, 6): ("Никулден", "Никола, Николай, Николина, Нина, Нико"),
    (12, 9): ("Анино зачатие", "Анна, Ана, Ани, Анелия"),
    (12, 17): ("Даниловден", "Данаил, Даниел, Даниела"),
    (12, 20): ("Игнажден", "Игнат, Игнатий, Огнян, Огняна, Искра"),
    (12, 25): ("Коледа", "Христо, Христина, Емануил, Радослав, Божидар"),
    (12, 27): ("Стефановден", "Стефан, Стефка, Стефания, Венцислав"),
}


@jarvis_tool
def name_day(name: str) -> str:
    """Умението "name_day" предоставя информация за имен дените на конкретни хора, като проверява дали
    съответната дата е празник или не. Използва се, когато искате да научите кога има имен ден за
    определено име (напр. „Кога е имен ден Георги?"). За разлика от справките за общи понятия, то се
    фокусира изключително върху лични празници.

    Args:
        name: Името.
    """
    wanted = name.strip().lower()
    for (month, day), (holiday, names) in NAME_DAYS.items():
        if wanted in (n.strip().lower() for n in names.split(",")):
            d = date(date.today().year, month, day)
            if d < date.today():
                d = d.replace(year=d.year + 1)
            return f"{name.capitalize()} празнува на {holiday} — {when.spoken_date(d)} ({day}.{month:02d})."
    return f"Не намирам имен ден за „{name}“ в календара ми (подвижните празници около Великден не са в него)."


@jarvis_tool
def todays_name_days() -> str:
    """Кой има имен ден днес (и следващият голям имен ден)."""
    today = date.today()
    entry = NAME_DAYS.get((today.month, today.day))
    upcoming = sorted((date(today.year + (1 if (m, d) < (today.month, today.day) else 0), m, d), v)
                      for (m, d), v in NAME_DAYS.items() if (m, d) != (today.month, today.day))[0]
    first = f"Днес е {entry[0]} — имен ден имат {entry[1]}. " if entry else "Днес няма голям имен ден. "
    return first + f"Следващият е {upcoming[1][0]} {when.spoken_date(upcoming[0])} ({upcoming[1][1]})."


_stopwatch: dict[str, float] = {}


@jarvis_tool
def stopwatch_start() -> str:
    """Пуска хронометър (засича колко време минава)."""
    _stopwatch["start"] = time.monotonic()
    return "Хронометърът тръгна."


@jarvis_tool
def stopwatch_stop() -> str:
    """Спира хронометъра и казва колко време е минало."""
    start = _stopwatch.pop("start", None)
    if start is None:
        return "Хронометърът не е пуснат."
    seconds = time.monotonic() - start
    return f"Минаха {int(seconds // 60)} минути и {seconds % 60:.1f} секунди."


@jarvis_tool
def pomodoro(minutes: int = 25) -> str:
    """Пуска помодоро: работа без прекъсване (25 минути), после Орион казва кога е почивката.

    Args:
        minutes: Колко минути работа (по подразбиране 25).
    """
    book.add("помодорото свърши — време е за 5 минути почивка", datetime.now() + timedelta(minutes=minutes))
    return f"Помодорото започна — {minutes} минути съсредоточена работа. Ще Ви кажа, когато свърши."


@jarvis_tool
def repeating_reminder(what: str, every_minutes: int, times: int = 8) -> str:
    """Напомняне, което се повтаря — напр. на всеки час да пиете вода или да станете от стола.

    Args:
        what: Какво да напомня, учтиво към сър, напр. "да пиете вода".
        every_minutes: През колко минути.
        times: Колко пъти общо (по подразбиране 8).
    """
    every_minutes = max(5, every_minutes)
    book.add(what, datetime.now() + timedelta(minutes=every_minutes), repeat_minutes=every_minutes, times=times)
    return f"Ще Ви напомням {what} на всеки {every_minutes} минути ({times} пъти)."
