"""
Умения за самоусъвършенстване: Орион се учи от забележките си и програмира сам себе си.

Този файл е защитен — Орион не може да го пренаписва (виж SkillForge.PROTECTED).
"""
from orion import orion_tool
from orion.self_improve import forge, lessons


@orion_tool
def learn_lesson(lesson: str) -> str:
    """Използвай ВИНАГИ, когато сър те поправи, каже че грешиш или обясни как трябва да се държиш
    или отговаряш. Записва трайна поука за поведението ти, за да не повтаряш грешката.
    (За факти за сър или света използвай remember.)

    Args:
        lesson: Поуката като кратко общо правило, напр. "Температурата винаги казвай в градуси Целзий."
    """
    count = lessons.add(lesson)
    return f"Поуката е записана завинаги. Вече знам {count} поуки."


@orion_tool
def list_lessons() -> str:
    """Изброява научените поуки, когато сър попита какво си научил от грешките си."""
    items = lessons.all()
    if not items:
        return "Все още нямам записани поуки."
    return " ".join(f"{i}. {l['text']}" for i, l in enumerate(items, 1))


@orion_tool
def forget_lesson(number: int) -> str:
    """Изтрива поука по номер, когато сър каже, че е грешна или вече не важи.

    Args:
        number: Номерът на поуката от list_lessons.
    """
    removed = lessons.remove(number)
    return f"Забравих поуката: {removed}" if removed else f"Няма поука с номер {number}."


@orion_tool
def create_skill(name: str, description: str) -> str:
    """Програмира НОВО умение за теб самия, когато сър поиска нещо, което не можеш да направиш
    с наличните умения (напр. „научи се да…“). Сър одобрява кода, след което умението става
    активно веднага и трябва да го използваш, за да изпълниш молбата.

    Args:
        name: Кратко име на английски в snake_case, напр. "get_bitcoin_price".
        description: Подробно на български какво трябва да прави умението, какви данни приема и какво връща.
    """
    return forge.create(name, description)


@orion_tool
def improve_skill(skill_name: str, problem: str) -> str:
    """Поправя или подобрява съществуващо умение, когато то върне грешка, работи неправилно
    или сър каже какъв е проблемът. След одобрение от сър опитай умението отново.

    Args:
        skill_name: Точното име на умението, напр. "get_weather".
        problem: Какво не е наред или какво трябва да се промени — думите на сър и текста на грешката.
    """
    return forge.improve(skill_name, problem)


@orion_tool
def undo_skill_change(skill_name: str) -> str:
    """Връща предишната версия на умение (или премахва ново умение), когато сър каже,
    че последната промяна е лоша.

    Args:
        skill_name: Името на умението.
    """
    return forge.undo(skill_name)


@orion_tool
def recent_errors() -> str:
    """Показва последните грешки на уменията, когато сър пита какво се е объркало
    или когато трябва да откриеш причината за проблем, преди да го поправиш."""
    return forge.recent_errors()
