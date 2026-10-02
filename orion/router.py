"""
Skill selection for each question.

The small model gets confused when it sees 50 skills at once: it picks the wrong one or none.
So the core skills are always offered, and the specialised groups (mail, computer,
vision, look-ups) only when the request or the previous reply contains a matching word.
Modules not listed here (the core ones and new ones written by Orion) are always available.
"""
import json
import re
import threading
from pathlib import Path

GROUPS = {
    "skills.google_skills": re.compile(
        r"писм|\bпоща|имейл|\bмейл|gmail|календар|\bсрещ|събити|ангажимент|задач|имам (утре|днес|да правя)|"
        r"график|отговори м|пиши на|прати на|изпрати", re.IGNORECASE),
    "skills.system_skills": re.compile(
        r"звук|по-силно|по-тихо|усили|намали|заглуш|пауза|спри |следващ|предишн|песента|музиката|"
        r"процесор|\bram\b|паметта на|диск|видеокарт|батерия|компютър|системата|затвори|заключи|рестарт|"
        r"изключи|приспи|снимка на екрана|скрийншот|клипборд|копира|постави|папка|файл|документ|свал|изтегл",
        re.IGNORECASE),
    "skills.vision_skills": re.compile(
        r"екран|виждаш|погледни|гледаш|снимка|картинка|прочети (ми )?(това|грешката)|какво пише|тази грешка",
        re.IGNORECASE),
    "skills.info_skills": re.compile(
        r"уикипеди|кой е|коя е|кои са|какво е|какво са|разкажи|валут|долар|евро|паунд|\bлев|франк|курс|"
        r"превърни|конвертирай|колко (са|е|прави)|км|мил|инч|фут|кил|градус|фаренхайт|литр|галон|декар|акр|"
        r"ютуб|youtube|пусни|песен|клип|музика", re.IGNORECASE),
    "skills.market_skills": re.compile(
        r"акци|борс|пазар|крипт|биткойн|биткоин|bitcoin|btc|етер|ethereum|солана|злато|сребро|петрол|нефт|"
        r"индекс|s&p|насдак|nasdaq|дау|форекс|forex|евро долар|eur|usd|паунд долар|инвест|тренд|rsi|macd|"
        r"графика|анализ|цената на|курса на|курсът на|csv|metatrader|мета трейдър|тесла|нвидия|епъл|"
        r"nvidia|tesla|apple|свещи|таймфрейм", re.IGNORECASE),
    "skills.claude_skills": re.compile(r"claude|клод|клауд", re.IGNORECASE),
    "skills.util_skills": re.compile(
        r"парол|случайн|монет|\bези\b|\bтура\b|\bзар|избери|qr|кю ар|брой думи|колко думи|base64|хеш|sha|md5|"
        r"двоич|шестнадес|осмич|бройна|римск|timestamp|unix|статистик|средно|медиана|с колко процента|"
        r"раздели|разделѝ|бакшиш|сметката", re.IGNORECASE),
    "skills.finance_skills": re.compile(
        r"кредит|заем|ипотек|вноск|лихв|спестя|ддс|отстъпк|гориво|бензин|дизел|разход|итм|телесна маса|"
        r"наднормено|колко да тежа", re.IGNORECASE),
    "skills.notes_skills": re.compile(
        r"бележк|запиши си|списък|списъка|пазарск|за пазара|купя|да купим|купих", re.IGNORECASE),
    "skills.time_skills": re.compile(
        r"\bдни\b|дата|какъв ден|кой ден|на колко години|възраст|рожден|изгрев|залез|луна|пълнолуние|празник|"
        r"почивен|почивни|имен ден|празнува|хронометър|засечи време|помодоро|на всеки|всеки час|повтаря",
        re.IGNORECASE),
    "skills.weather_skills": re.compile(
        r"прогноз|времето|вали|дъжд|чадър|въздух|замърсяв|фпч|\buv\b|ултравиолет|слънцезащит|по часове|седмицата",
        re.IGNORECASE),
    "skills.net_skills": re.compile(
        r"интернет|\bip\b|айпи|пинг|скорост|работи ли сайт|сайтът работи|wi-?fi|уай фай|мрежа|\bпорт(а|ът|ове)?\b|dns|"
        r"домейн|docker|докер|контейнер", re.IGNORECASE),
    "skills.file_skills": re.compile(
        r"файл|папк|документ|pdf|архив|zip|разархив|преименувай|премести|изтрий|място на диска|свободно място|"
        r"най-големи|кошче|временни|почисти|свалих|изтеглих|прочети (ми )?(документа|файла)", re.IGNORECASE),
    "skills.windows_skills": re.compile(
        r"прозор|отворен|какво работи|работят|бавен|бавно|натоварва|работния плот|минимизирай|настройк|"
        r"bluetooth|блутут|тъмен|светъл|режим|инсталиран|напиши в|диктувай|пиши в|версия на windows|уиндоус",
        re.IGNORECASE),
    "skills.places_skills": re.compile(
        r"държав|столица|население|разстояние|колко км|колко километра|маршрут|как да стигна|наблизо|аптека|"
        r"бензиностанция|ресторант|банкомат|карта|google maps|къде се намира", re.IGNORECASE),
    "skills.media_skills": re.compile(r"радио|spotify|спотифай|музика|песен|песни|плейлист", re.IGNORECASE),
    "skills.reels_skills": re.compile(
        r"youtu|ютуб|рийл|reel|шортс|shorts|изрежи|изрязва|клипа|клипове|видеото|моменти|хайлайт|highlight|"
        r"авторски права|копирайт|creative commons|свободни видеа|свободни клипове|лиценз",
        re.IGNORECASE),
    "skills.trading_skills": re.compile(
        r"сравни|страх|алчност|портфейл|известие|кажи ми когато|кажи ми, когато|стигне|надмине|падне под|"
        r"победител|губещ|растат|падат|акции|в евро|в лева|биткойн|крипт|етер", re.IGNORECASE),
    "skills.language_skills": re.compile(
        r"преведи|превод|на английски|на немски|на френски|на руски|на какъв език|какво означава|значение|думата",
        re.IGNORECASE),
    "skills.assistant_skills": re.compile(
        r"брифинг|добро утро|какво ме чака|какво можеш|умения|какво умееш|способност", re.IGNORECASE),
}


# Words Orion learned by itself in test mode (orion/self_test.py): a request with such a word was not
# understood because its group was hidden. Kept separately so they are easy to see and remove.
LEARNED_FILE = Path(__file__).resolve().parent.parent / "memory" / "learned_routes.json"
_learned: dict = {"mtime": None, "words": {}}
_lock = threading.Lock()


def learned() -> dict[str, list[str]]:
    """{module: [words]} from memory/learned_routes.json (re-read if the file changed)."""
    try:
        mtime = LEARNED_FILE.stat().st_mtime
    except OSError:
        return {}
    with _lock:
        if mtime != _learned["mtime"]:
            try:
                words = json.loads(LEARNED_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                words = {}
            _learned.update(mtime=mtime, words=words if isinstance(words, dict) else {})
        return _learned["words"]


def learn(module: str, word: str) -> None:
    """Adds a word that from now on shows the group `module`."""
    words = {m: list(w) for m, w in learned().items()}
    if word not in words.setdefault(module, []):
        words[module].append(word)
        LEARNED_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEARNED_FILE.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")


def excluded_modules(user_text: str, previous_text: str = "",
                     extra: dict[str, list[str]] | None = None) -> set[str]:
    """The skill modules that must NOT be offered to the model for this request.
    `extra` — more trial words (test mode checks a word before learning it)."""
    text = f"{previous_text} {user_text}"
    lower = text.lower()
    words = learned()

    def shown(module: str, pattern: re.Pattern) -> bool:
        more = words.get(module, []) + (extra or {}).get(module, [])
        return bool(pattern.search(text)) or any(w in lower for w in more)

    return {module for module, pattern in GROUPS.items() if not shown(module, pattern)}
