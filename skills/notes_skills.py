"""
Бележки и списъци (пазарски, за пътуване, за филми…) — пазят се на този компютър,
в memory/notes.json. За трайни факти за сър е „remember“, тук са нещата за вършене.
"""
import json
import threading
from datetime import datetime
from pathlib import Path

from orion import orion_tool
from orion.apps import normalize

FILE = Path(__file__).resolve().parent.parent / "memory" / "notes.json"
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"notes": [], "lists": {}}


def _save(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _list_name(name: str) -> str:
    """„пазарския“, „за пазара“, „покупки“ -> „пазарски“; „пътуването“ -> „пътуване“."""
    name = normalize(name) or "пазарски"
    if name.startswith(("пазар", "покупк", "магазин")):
        return "пазарски"
    return name


@orion_tool
def save_note(text: str, title: str = "") -> str:
    """Записва бележка (идея, код, номер, текст за после). За „запиши си бележка…“.

    Args:
        text: Съдържанието на бележката.
        title: Кратко заглавие (по желание).
    """
    with _lock:
        data = _load()
        data["notes"].append({"title": title.strip() or text.strip()[:40], "text": text.strip(),
                              "time": f"{datetime.now():%d.%m.%Y %H:%M}"})
        _save(data)
        return f"Записах бележката. Имате {len(data['notes'])} бележки."


@orion_tool
def list_notes() -> str:
    """Кои бележки има — заглавията, с номера."""
    notes = _load()["notes"]
    if not notes:
        return "Нямате бележки."
    return "Бележки: " + "; ".join(f"{i}. {n['title']} ({n['time']})" for i, n in enumerate(notes, 1)) + "."


@orion_tool
def read_note(number: int = 0, search: str = "") -> str:
    """Прочита бележка по номер или по дума от нея.

    Args:
        number: Номерът от list_notes (0 — последната).
        search: Или дума от бележката.
    """
    notes = _load()["notes"]
    if not notes:
        return "Нямате бележки."
    if search:
        found = [n for n in notes if search.lower() in (n["title"] + n["text"]).lower()]
        if not found:
            return f"Няма бележка с „{search}“."
        note = found[-1]
    else:
        note = notes[number - 1] if 1 <= number <= len(notes) else notes[-1]
    return f"Бележка „{note['title']}“ от {note['time']}: {note['text']}"


@orion_tool
def delete_note(number: int = 0, search: str = "") -> str:
    """Изтрива бележка по номер или по дума от нея.

    Args:
        number: Номерът от list_notes.
        search: Или дума от бележката.
    """
    with _lock:
        data = _load()
        notes = data["notes"]
        index = next((i for i, n in enumerate(notes) if search and search.lower() in (n["title"] + n["text"]).lower()),
                     number - 1 if 1 <= number <= len(notes) else None)
        if index is None:
            return "Не намерих такава бележка."
        removed = notes.pop(index)
        _save(data)
        return f"Изтрих бележката „{removed['title']}“."


@orion_tool
def add_to_list(items: str, list_name: str = "пазарски") -> str:
    """Добавя неща в списък — пазарски (по подразбиране) или друг: „за пътуването“, „филми“…

    Args:
        items: Какво да добави, разделено със запетаи, напр. "мляко, хляб, яйца".
        list_name: Кой списък.
    """
    name = _list_name(list_name)
    new = [i.strip() for i in items.replace(" и ", ",").split(",") if i.strip()]
    with _lock:
        data = _load()
        current = data["lists"].setdefault(name, [])
        current.extend(i for i in new if i.lower() not in (c.lower() for c in current))
        _save(data)
        return f"Добавих в списък „{name}“: {', '.join(new)}. Вече има {len(current)} неща."


@orion_tool
def show_list(list_name: str = "пазарски") -> str:
    """Какво има в списък (пазарски по подразбиране).

    Args:
        list_name: Кой списък.
    """
    name = _list_name(list_name)
    items = _load()["lists"].get(name, [])
    return f"В списък „{name}“: {', '.join(items)}." if items else f"Списък „{name}“ е празен."


@orion_tool
def remove_from_list(items: str, list_name: str = "пазарски") -> str:
    """Маха неща от списък (купени, свършени).

    Args:
        items: Какво да махне, разделено със запетаи.
        list_name: Кой списък.
    """
    name = _list_name(list_name)
    drop = {normalize(i) for i in items.replace(" и ", ",").split(",") if i.strip()}  # „хляба“ = „хляб“
    with _lock:
        data = _load()
        current = data["lists"].get(name, [])
        kept = [c for c in current if normalize(c) not in drop]
        data["lists"][name] = kept
        _save(data)
        return f"Махнах {len(current) - len(kept)} неща. В „{name}“ остават: {', '.join(kept) or 'нищо'}."


@orion_tool
def clear_list(list_name: str = "пазарски") -> str:
    """Изчиства целия списък.

    Args:
        list_name: Кой списък.
    """
    name = _list_name(list_name)
    with _lock:
        data = _load()
        data["lists"][name] = []
        _save(data)
    return f"Изчистих списък „{name}“."


@orion_tool
def all_lists() -> str:
    """Кои списъци има и колко неща има във всеки."""
    lists = _load()["lists"]
    if not lists:
        return "Нямате списъци."
    return "Списъци: " + "; ".join(f"{n} ({len(items)})" for n, items in lists.items()) + "."
