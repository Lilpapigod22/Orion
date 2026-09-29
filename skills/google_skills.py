"""
Google Календар, Gmail и Google Задачи. Връзката се настройва с „Орион, свържи Google“.

Писма се изпращат и събития се изтриват само след като сър натисне бутона в прозореца.
"""
from datetime import date, datetime, time, timedelta

from orion import apps, confirm, google, orion_tool, when
from orion.google import GoogleError

# Последният прочетен списък с писма — за „прочети второто“.
_last_mail: list[dict] = []


def _google(action: str, **params):
    """Като google.call, но проблемите стават текст за сър, а не „грешка в умението“ —
    иначе Орион би се опитал да „поправя“ кода си заради липсващ интернет."""
    try:
        return google.call(action, **params), None
    except GoogleError as e:
        return None, str(e)


def _local(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


def _sender(address: str) -> str:
    """„Иван Петров <ivan@x.com>“ -> „Иван Петров“."""
    name = address.split("<")[0].strip().strip('"')
    return name or address.strip("<> ")


# --- Календар -------------------------------------------------------------------------------
def _describe_event(ev: dict) -> str:
    where = f" ({ev['location']})" if ev.get("location") else ""
    if ev["allDay"]:
        return f"цял ден — {ev['title']}{where}"
    start, end = _local(ev["start"]), _local(ev["end"])
    return f"{start:%H:%M}–{end:%H:%M} {ev['title']}{where}"


@orion_tool
def calendar_events(day: str = "днес", days: int = 1) -> str:
    """Поискайте „Какво има в календара ми за утре?/" или „Кои срещи имам днес?", за да видите вашите
    събития и напомняния от Google Календар. Умението показва детайли за планираните ви дейности за
    конкретни дни или период.

    Args:
        day: От кой ден, както го е казал сър: "днес", "утре", "в петък", "25 октомври".
        days: За колко дни, напр. 7 за цялата седмица.
    """
    first = when.parse_date(day) or date.today()
    start = datetime.combine(first, time(0, 0)).astimezone()
    end = start + timedelta(days=max(1, days))
    events, problem = _google("calendar_list", start=start.isoformat(), end=end.isoformat())
    if problem:
        return problem
    period = when.spoken_date(first) if days <= 1 else f"{days} дни от {when.spoken_date(first)}"
    if not events:
        return f"Няма събития {period}."
    if days <= 1:
        return f"Събития {period}: " + "; ".join(_describe_event(ev) for ev in events) + "."
    by_day: dict[str, list[str]] = {}
    for ev in events:
        day_key = ev["start"][:10] if ev["allDay"] else f"{_local(ev['start']):%Y-%m-%d}"
        by_day.setdefault(when.spoken_date(date.fromisoformat(day_key)), []).append(_describe_event(ev))
    return f"Събития за {period}: " + " | ".join(f"{d}: {'; '.join(items)}" for d, items in by_day.items()) + "."


@orion_tool
def calendar_add_event(title: str, day: str, start_time: str = "", duration_minutes: int = 60,
                       location: str = "") -> str:
    """Записва събитие или среща в Google календара на сър.

    Args:
        title: Заглавие, напр. "Среща със Стефан".
        day: Ден, както го е казал сър: "утре", "в петък", "25 октомври", "25.10".
        start_time: Начален час, напр. "15:00" или "3 следобед". Празно — събитие за целия ден.
        duration_minutes: Продължителност в минути (по подразбиране 60).
        location: Място, ако е казано.
    """
    event_day = when.parse_date(day)
    if not event_day:
        return f"Не разбрах кой ден е „{day}“, сър. Кажете напр. „утре“, „в петък“ или „25 октомври“."
    moment = when.parse_time(start_time) if start_time else None
    if start_time and not moment:
        return f"Не разбрах в колко часа е „{start_time}“, сър."
    if moment:
        start = datetime.combine(event_day, moment).astimezone()
        end = start + timedelta(minutes=duration_minutes or 60)
        _, problem = _google("calendar_create", title=title, start=start.isoformat(), end=end.isoformat(),
                             location=location)
        period = f"{when.spoken_date(event_day)} от {start:%H:%M} до {end:%H:%M}"
    else:
        _, problem = _google("calendar_create", title=title, allDay=True, date=event_day.isoformat(),
                             location=location)
        period = f"{when.spoken_date(event_day)}, за целия ден"
    return problem or f"Записах „{title}“ в календара — {period}."


@orion_tool
def calendar_delete_event(title: str, day: str) -> str:
    """Изтрива събитие от Google календара (сър потвърждава с бутон).

    Args:
        title: Дума от заглавието на събитието, напр. "Стефан".
        day: В кой ден е, напр. "утре".
    """
    event_day = when.parse_date(day)
    if not event_day:
        return f"Не разбрах кой ден е „{day}“, сър."
    start = datetime.combine(event_day, time(0, 0)).astimezone()
    events, problem = _google("calendar_list", start=start.isoformat(),
                              end=(start + timedelta(days=1)).isoformat())
    if problem:
        return problem
    matches = [ev for ev in events if title.lower() in ev["title"].lower()]
    if not matches:
        return f"Не намерих събитие „{title}“ {when.spoken_date(event_day)}."
    ev = matches[0]
    if not confirm.ask("Изтриване от календара", f"{when.spoken_date(event_day)} · {_describe_event(ev)}",
                       "", "Изтрий"):
        return "Сър отказа изтриването — събитието остава."
    _, problem = _google("calendar_delete", id=ev["id"])
    return problem or f"Изтрих „{ev['title']}“ от календара."


# --- Поща -------------------------------------------------------------------------------------
@orion_tool
def check_email(search: str = "") -> str:
    """Проверява пощата (Gmail) на сър: новите непрочетени писма — от кого са и за какво.

    Args:
        search: Празно — новите писма. Или търсене в пощата, напр. "от Иван" или "фактура".
    """
    query = None
    if search.strip():
        words = search.strip()
        query = f"from:({words[3:]})" if words.lower().startswith("от ") else words
    mails, problem = _google("mail_list", query=query, max=5)
    if problem:
        return problem
    _last_mail[:] = mails
    if not mails:
        return "Няма нови писма." if not search else f"Няма писма за „{search}“."
    lines = [f"{i}. от {_sender(m['from'])}: „{m['subject'] or 'без тема'}“ — {m['snippet'][:120]}"
             for i, m in enumerate(mails, 1)]
    head = "Нови писма" if not search else f"Писма за „{search}“"
    return f"{head} ({len(mails)}): " + " ".join(lines)


@orion_tool
def read_email(number: int = 1) -> str:
    """Прочита цялото писмо от последния списък на check_email.

    Args:
        number: Кое писмо от списъка — 1 за първото.
    """
    if not _last_mail:
        return "Първо проверете пощата — нямам списък с писма."
    if not 1 <= number <= len(_last_mail):
        return f"В списъка има {len(_last_mail)} писма."
    mail, problem = _google("mail_read", id=_last_mail[number - 1]["id"])
    if problem:
        return problem
    return (f"Писмо от {mail['from']}, тема „{mail['subject']}“, {_local(mail['date']):%d.%m %H:%M}:\n"
            f"{mail['body']}")


def _find_address(to: str) -> tuple[str | None, str]:
    """(имейл, как да се покаже) по име или адрес."""
    if "@" in to:
        return to.strip(), to.strip()
    names = list(dict.fromkeys([to.strip(), apps.to_latin(to.strip()).title()]))
    contacts, _ = _google("contact_find", names=names)
    if not contacts:
        return None, to
    best = contacts[0]
    return best["email"], f"{best['name']} <{best['email']}>" if best["name"] else best["email"]


@orion_tool
def send_email(to: str, subject: str, body: str) -> str:
    """Изпраща ново писмо от Gmail на сър. Писмото тръгва само ако сър натисне „Изпрати“.

    Args:
        to: Имейл адрес или име на човек, на когото сър е писал преди, напр. "Иван".
        subject: Тема на писмото.
        body: Текстът на писмото — учтив, завършен, от името на сър.
    """
    address, shown = _find_address(to)
    if not address:
        return f"Не намерих имейл адреса на „{to}“ в пощата Ви, сър. Кажете ми адреса."
    if not confirm.ask("Изпращане на писмо", f"До: {shown} · Тема: {subject}", body, "Изпрати"):
        return "Сър не одобри писмото — не е изпратено."
    _, problem = _google("mail_send", to=address, subject=subject, body=body)
    return problem or f"Писмото до {shown} е изпратено."


@orion_tool
def reply_email(number: int, body: str) -> str:
    """Отговаря на писмо от последния списък на check_email (след „Изпрати“ от сър).

    Args:
        number: На кое писмо от списъка — 1 за първото.
        body: Текстът на отговора — учтив и завършен, от името на сър.
    """
    if not _last_mail or not 1 <= number <= len(_last_mail):
        return "Първо проверете пощата — нямам такова писмо в списъка."
    mail = _last_mail[number - 1]
    if not confirm.ask("Отговор на писмо", f"До: {mail['from']} · Тема: Re: {mail['subject']}", body, "Изпрати"):
        return "Сър не одобри отговора — не е изпратен."
    _, problem = _google("mail_send", replyToId=mail["id"], body=body)
    return problem or f"Отговорих на {_sender(mail['from'])}."


# --- Задачи ---------------------------------------------------------------------------------
@orion_tool
def tasks_list() -> str:
    """Списъкът със задачи на сър (Google Tasks) — какво има да свърши."""
    tasks, problem = _google("tasks_list")
    if problem:
        return problem
    if not tasks:
        return "Нямате незавършени задачи."
    return "Задачи: " + "; ".join(
        t["title"] + (f" (до {when.spoken_date(date.fromisoformat(t['due']))})" if t["due"] else "")
        for t in tasks) + "."


@orion_tool
def tasks_add(title: str, due: str = "") -> str:
    """Добавя задача в списъка на сър (Google Tasks), напр. „купи мляко“.

    Args:
        title: Задачата, кратко, напр. "Купи мляко".
        due: Срок, ако е казан: "утре", "в петък". Празно — без срок.
    """
    due_day = when.parse_date(due) if due else None
    _, problem = _google("tasks_add", title=title, due=due_day.isoformat() if due_day else "")
    if problem:
        return problem
    return f"Добавих задачата „{title}“" + (f" със срок {when.spoken_date(due_day)}." if due_day else ".")


@orion_tool
def tasks_complete(title: str) -> str:
    """Отбелязва задача като свършена.

    Args:
        title: Дума от задачата, напр. "мляко".
    """
    tasks, problem = _google("tasks_list")
    if problem:
        return problem
    matches = [t for t in tasks if title.lower() in t["title"].lower()]
    if not matches:
        return f"Не намерих задача „{title}“."
    _, problem = _google("tasks_complete", id=matches[0]["id"])
    return problem or f"Отбелязах „{matches[0]['title']}“ като свършена."
