"""
Dates and times said in Bulgarian: „утре“, „следващия вторник“, „25 октомври“, „3 следобед“,
„след 20 минути“ (tomorrow, next Tuesday, 25 October, 3 pm, in 20 minutes). Used by the calendar, tasks and reminders.

The model passes these words as sir said them — the date is worked out here, in code,
because small models often get wrong which date “next Tuesday” is.
"""
import re
from datetime import date, datetime, time, timedelta

from .clock import MONTHS, WEEKDAYS

_WEEKDAY_FORMS = {
    **{d: i for i, d in enumerate(WEEKDAYS)},
    "понеделника": 0, "вторника": 1, "четвъртъка": 3, "петъка": 4, "съботата": 5, "неделята": 6,
}
_MONTH_STEMS = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}  # „яну“, „фев“…, „сеп“
_NUMBER_WORDS = {
    "един": 1, "една": 1, "едно": 1, "два": 2, "две": 2, "три": 3, "четири": 4, "пет": 5, "шест": 6,
    "седем": 7, "осем": 8, "девет": 9, "десет": 10, "единадесет": 11, "единайсет": 11,
    "дванадесет": 12, "дванайсет": 12, "петнадесет": 15, "петнайсет": 15, "двадесет": 20,
    "двайсет": 20, "тридесет": 30, "трийсет": 30, "четиридесет": 40, "четирсет": 40,
    "петдесет": 50, "шестдесет": 60, "деветдесет": 90,
}


def _numbers(text: str) -> str:
    """„двадесет минути“ -> „20 минути“ (simple numbers, as speech recognition writes them)."""
    return re.sub(r"\b(" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")\b",
                  lambda m: str(_NUMBER_WORDS[m.group(1)]), text)


def parse_date(text: str, today: date | None = None) -> date | None:
    """The date in the text, or None. „утре“, „в петък“, „следващата сряда“, „25.10“, „25 октомври“."""
    today = today or date.today()
    t = text.lower().strip()
    if m := re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        return date(int(m[1]), int(m[2]), int(m[3]))
    for m in re.finditer(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", t):
        year = int(m[3]) if m[3] else today.year
        year += 2000 if year < 100 else 0
        try:
            result = date(year, int(m[2]), int(m[1]))
        except ValueError:  # „10.30“ is a time, not a date
            continue
        return result.replace(year=result.year + 1) if not m[3] and result < today else result
    if m := re.search(r"\b(\d{1,2})(?:-?[ао]?\s*|-ти\s*|-ви\s*|-ри\s*|\s+)([а-я]{3})[а-я]*\b", t):
        month = _MONTH_STEMS.get(m[2])
        if month:
            result = date(today.year, month, int(m[1]))
            return result.replace(year=result.year + 1) if result < today else result
    if re.search(r"\bвдругиден\b|\bдруги ден\b", t):
        return today + timedelta(days=2)
    if re.search(r"\bутре\b", t):
        return today + timedelta(days=1)
    if re.search(r"\bднес\b|\bтази вечер\b|\bдовечера\b", t):
        return today
    for word, weekday in _WEEKDAY_FORMS.items():
        if re.search(rf"\b{word}\b", t):
            days = (weekday - today.weekday()) % 7
            if re.search(r"\bследващ", t):
                days = days or 7
                days += 7 if days < 7 and re.search(r"\bседмица", t) else 0
            return today + timedelta(days=days)
    if re.search(r"\bследващата седмица\b", t):
        return today + timedelta(days=7 - today.weekday())  # next Monday
    return None


def parse_time(text: str) -> time | None:
    """The time in the text, or None. „15:30“, „в 3 следобед“, „8 и половина вечерта“, „по обяд“."""
    t = _numbers(text.lower())
    if re.search(r"\bпо обяд\b|\bна обяд\b", t) and not re.search(r"\d", t):
        return time(12, 0)
    patterns = (
        r"\b(\d{1,2}):(\d{2})\b",
        # „в 10.30“ — with a dot only after a preposition, otherwise „10.10“ would be both a date and a time.
        r"\b(?:в|към|около|от|до)\s+(\d{1,2})\.(\d{2})\b",
        r"\b(?:в|към|около|от|до)\s+(\d{1,2})(?:\s*ч(?:аса|\.)?)?(?:\s+и\s+(половина|\d{1,2}))?(?![.\d])",
        r"\b(\d{1,2})\s*(?:ч\.|часа)(?:\s+и\s+(половина|\d{1,2}))?",
        r"\b(\d{1,2})(?:\s+и\s+(половина|\d{1,2}))?\s+(?=сутринта|следобед|вечерта|през нощта)",
    )
    for pattern in patterns:
        for m in re.finditer(pattern, t):
            hour = int(m[1])
            minute = 30 if m[2] == "половина" else int(m[2] or 0)
            if hour < 12 and re.search(r"следобед|вечерта|довечера|тази вечер", t):
                hour += 12
            if hour <= 23 and minute <= 59:
                return time(hour, minute)
    return None


def parse_in(text: str) -> timedelta | None:
    """An interval „след/за 20 минути“, „след час и половина“, „2 часа“ or None."""
    t = _numbers(text.lower())
    if re.search(r"\bполовин час\b", t):
        return timedelta(minutes=30)
    hours = re.search(r"(\d+(?:[.,]5)?)\s*час|\bчас\b", t)
    minutes = re.search(r"(\d+)\s*мин", t)
    seconds = re.search(r"(\d+)\s*сек", t)
    if not (hours or minutes or seconds):
        return None
    total = timedelta()
    if hours:
        total += timedelta(hours=float(hours[1].replace(",", ".")) if hours.lastindex else 1)
        if re.search(r"час\w*\s+и\s+половина", t):
            total += timedelta(minutes=30)
    if minutes:
        total += timedelta(minutes=int(minutes[1]))
    if seconds:
        total += timedelta(seconds=int(seconds[1]))
    return total


def parse_moment(text: str, now: datetime | None = None) -> datetime | None:
    """An exact moment: „след 20 минути“, „в 18:00“ (today, or tomorrow if it has passed), „утре в 9“."""
    now = now or datetime.now()
    if re.search(r"\b(след|за)\b", text.lower()) or not (parse_date(text, now.date()) or parse_time(text)):
        delta = parse_in(text)
        if delta:
            return now + delta
    day, moment = parse_date(text, now.date()), parse_time(text)
    if not moment:
        return datetime.combine(day, time(9, 0)) if day else None
    result = datetime.combine(day or now.date(), moment)
    if not day and result <= now:
        # „в 7“ said at 10 am is 19:00 today; if that has passed too — tomorrow.
        evening = result + timedelta(hours=12)
        if moment.hour < 12 and evening > now and "сутрин" not in text.lower():
            return evening
        result += timedelta(days=1)
    return result


def spoken_date(d: date, today: date | None = None) -> str:
    """„днес“, „утре“, „в събота, 27 септември“."""
    today = today or date.today()
    if d == today:
        return "днес"
    if d == today + timedelta(days=1):
        return "утре"
    prefix = "във" if d.weekday() == 1 else "в"  # „във вторник“, but „в сряда“
    return f"{prefix} {WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"
