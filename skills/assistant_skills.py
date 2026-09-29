"""
Асистентът: сутрешен брифинг (всичко важно за деня наведнъж) и „какво можеш“ — уменията по групи.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from orion import clock, google, orion_tool, registry

GROUPS = {
    "skills.basic_skills": "Основни (час, сметки, програми, сайтове, време навън)",
    "skills.web_skills": "Интернет (търсене, четене на страници)",
    "skills.info_skills": "Справки (Уикипедия, валути, мерни единици, YouTube)",
    "skills.google_skills": "Google (поща, календар, задачи)",
    "skills.reminder_skills": "Напомняния и таймери",
    "skills.time_skills": "Дати и време (празници, имени дни, изгрев, Луна, хронометър)",
    "skills.weather_skills": "Прогноза (седмица, по часове, дъжд, въздух, UV)",
    "skills.system_skills": "Компютърът (звук, музика, изключване, файлове, клипборд)",
    "skills.windows_skills": "Windows (прозорци, настройки, тъмен режим, писане на текст)",
    "skills.file_skills": "Файлове (големи файлове, почистване, архиви, документи)",
    "skills.vision_skills": "Зрение (екранът и снимки)",
    "skills.market_skills": "Пазари (цени, анализ с графика, крипто)",
    "skills.trading_skills": "Търговия (известия за цени, портфейл, страх и алчност)",
    "skills.game_skills": "Игри",
    "skills.claude_skills": "Claude",
    "skills.net_skills": "Мрежа (скорост на интернета, IP, пинг, портове, Docker)",
    "skills.places_skills": "Места (държави, разстояния, маршрути, карти)",
    "skills.media_skills": "Музика+ (радио, Spotify, музиката на компютъра)",
    "skills.notes_skills": "Бележки и списъци",
    "skills.util_skills": "Инструменти (пароли, зар, QR код, кодиране, статистика)",
    "skills.finance_skills": "Калкулатори (кредит, лихва, ДДС, гориво, ИТМ)",
    "skills.language_skills": "Езици (превод, значение на думи)",
    "skills.memory_skills": "Памет",
    "skills.self_improvement": "Самоусъвършенстване (учи се, пише нови умения)",
    "skills.assistant_skills": "Асистент (брифинг, умения)",
}


@orion_tool
def list_skills(group: str = "") -> str:
    """Какво може Орион — уменията по групи, или подробно за една група. За „какво можеш“.

    Args:
        group: Дума от групата, напр. "пазари" (празно — всички групи с броя умения).
    """
    by_module: dict[str, list[str]] = {}
    for name in registry.names():
        by_module.setdefault(registry._tools[name]["module"], []).append(name)
    if group.strip():
        module = next((m for m, label in GROUPS.items() if group.lower() in label.lower()), None)
        if not module:
            return f"Няма група „{group}“."
        details = [registry._tools[n]["schema"]["function"]["description"].split("\n")[0].split(". ")[0]
                   for n in by_module.get(module, [])]
        return f"{GROUPS[module]}: " + "; ".join(details) + "."
    rows = [f"{label} — {len(by_module.get(module, []))}" for module, label in GROUPS.items() if by_module.get(module)]
    own = sum(len(v) for m, v in by_module.items() if m not in GROUPS)
    if own:
        rows.append(f"Умения, които съм написал сам — {own}")
    return f"Имам {len(registry.names())} умения: " + "; ".join(rows) + "."


def _safe(tool: str, **arguments) -> str:
    result = registry.call(tool, arguments)
    return "" if result.startswith("Грешка") else result


@orion_tool
def daily_briefing() -> str:
    """Сутрешен брифинг: датата, времето, напомнянията, календарът и пощата (ако Google е свързан),
    пазарите и имените дни — всичко важно за деня наведнъж. За „добро утро“, „какво ме чака днес“."""
    jobs = {"weather": ("get_weather", {"day": "днес"}), "reminders": ("list_reminders", {}),
            "names": ("todays_name_days", {}), "markets": ("market_overview", {})}
    if google.is_connected():
        jobs |= {"calendar": ("calendar_events", {"day": "днес"}), "mail": ("check_email", {}),
                 "tasks": ("tasks_list", {})}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {key: pool.submit(_safe, tool, **args) for key, (tool, args) in jobs.items()}
        found = {key: f.result() for key, f in futures.items()}
    now = datetime.now()
    parts = [f"Днес е {clock.date_text(now)}, часът е {clock.time_text(now)}."]
    for key in ("weather", "calendar", "tasks", "mail", "reminders", "names", "markets"):
        if found.get(key):
            parts.append(found[key])
    return "Брифинг: " + " ".join(parts) + " (Преразкажи накратко, най-важното първо.)"
