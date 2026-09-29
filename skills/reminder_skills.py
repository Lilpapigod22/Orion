"""
Умения за напомняния и таймери. Митко ги казва на глас, когато стане време.
"""
from datetime import datetime

from jarvis import jarvis_tool, when
from jarvis.reminders import book


def describe_due(due: datetime, now: datetime | None = None) -> str:
    """„в 18:30 днес“, „след 20 минути“, „в 9:00 утре“."""
    now = now or datetime.now()
    minutes = round((due - now).total_seconds() / 60)
    if 0 <= minutes < 60:
        return f"след {minutes} минути" if minutes != 1 else "след 1 минута"
    return f"{when.spoken_date(due.date(), now.date())} в {due:%H:%M}"


@jarvis_tool
def set_reminder(what: str, when_text: str) -> str:
    """Слага напомняне или будилник чрез гласови команди за конкретни действия в бъдеще време, като
    „Напомни ми след 20 минути да изключа фурната", „Събуди ме утре в седем" или „Запиши ми среща за
    петък".

    Args:
        what: Какво да напомни, учтиво към сър, напр. "да изключите фурната".
        when_text: Кога, както го е казал сър: "след 20 минути", "в 18:30", "утре в 9".
    """
    due = when.parse_moment(when_text)
    if not due:
        raise ValueError(f"не разбирам кога е „{when_text}“ — кажете напр. „след 20 минути“ или „в 18:30“")
    book.add(what, due)
    return f"Ще Ви напомня {describe_due(due)}: {what}."


@jarvis_tool
def set_timer(duration: str) -> str:
    """Пуска таймер (обратно броене). За „таймер за 10 минути“, „засечи 5 минути“.

    Args:
        duration: Колко време, напр. "10 минути", "час и половина", "30 секунди".
    """
    delta = when.parse_in(duration)
    if not delta:
        raise ValueError(f"не разбирам колко време е „{duration}“")
    book.add(duration.strip(), datetime.now() + delta, kind="timer")
    return f"Таймерът за {duration.strip()} тръгна."


@jarvis_tool
def list_reminders() -> str:
    """Казва кои напомняния и таймери чакат."""
    items = book.pending()
    if not items:
        return "Няма чакащи напомняния."
    return "Чакащи напомняния: " + "; ".join(
        f"{describe_due(datetime.fromisoformat(i['due']))} — "
        f"{'таймер ' + i['text'] if i['kind'] == 'timer' else i['text']}" for i in items) + "."


@jarvis_tool
def cancel_reminder(what: str = "") -> str:
    """Отменя напомняне или таймер.

    Args:
        what: Дума от напомнянето, напр. "фурната". Празно — отменя всички.
    """
    removed = book.cancel(what)
    if not removed:
        return f"Няма напомняне, което съдържа „{what}“."
    return f"Отмених {len(removed)} " + ("напомняне." if len(removed) == 1 else "напомняния.")
