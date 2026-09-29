"""
Рефлекси — мигновени и винаги верни отговори на най-честите команди, без езиковия модел.

Малките локални модели понякога бъркат деня от седмицата или „казват“, че са отворили
програма, без да са го направили. Затова часът, датата, отварянето на програми и сайтове,
търсенето в Google/YouTube, времето навън, таймерите, връзката с Google и затварянето на
JARVIS се разпознават тук с прости правила. Всичко, което не пасва точно, отива при модела.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote_plus

import config

from . import apps, clock, google, reels, when


@dataclass
class Reflex:
    answer: str = ""
    tool: str | None = None        # умение, което да се изпълни (минава през регистъра)
    arguments: dict | None = None
    # Действие на приложението: "close" (изключване), "google_setup", "google_connect".
    action: str | None = None

    @property
    def arguments_json(self) -> str:
        return json.dumps(self.arguments or {}, ensure_ascii=False)


# Думи, които не променят смисъла на въпроса: „Орион, кажи ми моля колко е часът сега?“
_FILLER = set(config.WAKE_WORDS) | {
    "моля", "те", "ей", "хей", "бе", "де",
    "братле", "брат", "сър", "кажи", "кажете", "кажеш", "ми", "можеш", "можете", "може", "ли", "да",
    "би", "казал", "искам", "знам", "сега", "в", "момента", "точно", "точния", "точният", "точната",
    "ако", "обичаш", "обичате", "бързо", "веднага", "я", "а", "добре",
}
# Въпрос за час/дата/ден: всички думи са от тези + поне една тема. Иначе („колко е часът
# в Ню Йорк“, „кой ден беше вчера“) въпросът отива при модела.
_GLUE = {"колко", "е", "кой", "коя", "кое", "какъв", "каква", "какво", "днес", "сме", "от", "и", "на",
         "стана", "седмицата", "седмица"}
_TIME = {"час", "часа", "часът"}
_DATE = {"дата", "датата", "число", "числото"}
_DAY = {"ден", "денят", "деня"}

_OPEN_RE = re.compile(
    r"(?:ми\s+)?(?:отвори|отворете|отвориш|отворите|пусни|пуснете|пуснеш|стартирай|стартирайте|стартираш|"
    r"включи|включете|покажи|покажете)(?:\s+ми)?\s+(?P<target>.+)",
    re.IGNORECASE,
)
_WEATHER_RE = re.compile(
    r"(?:какво|как|какво е|как е)\s+(?:е\s+)?времето(?:\s+(?:днес|навън|сега|в момента))*"
    r"(?:\s+(?:в|във)\s+(?P<city>[\w\s\-]+?))?(?:\s+(?:днес|навън|сега))?",
    re.IGNORECASE,
)
_CLOSE = {
    "затвори се", "самозатвори се", "изключи се", "самоизключи се", "излез", "изход", "довиждане",
    "затвори програмата", "изключи програмата", "спри програмата", "exit", "quit",
}


_WAKE_RE = re.compile(r"\b(" + "|".join(config.WAKE_WORDS) + r")\b[\s,.!?]*", re.IGNORECASE)
_SEARCH_SITES = {"гугъл": "google", "google": "google", "youtube": "youtube", "ютуб": "youtube", "ютюб": "youtube"}
_SITE_WORDS = "|".join(_SEARCH_SITES)
_SEARCH_RES = (
    re.compile(rf"(?:потърси|потърсете|търси|намери|намерете)(?:\s+ми)?\s+(?:в|във|на)\s+(?P<site>{_SITE_WORDS})"
               rf"\s+(?P<query>.+)", re.IGNORECASE),
    re.compile(rf"(?:потърси|потърсете|търси|намери|намерете|пусни|пуснете)(?:\s+ми)?\s+(?P<query>.+?)"
               rf"\s+(?:в|във|на|от)\s+(?P<site>{_SITE_WORDS})", re.IGNORECASE),
)
_TIMER_RES = (
    re.compile(r"(?:(?:сложи|пусни|включи|направи|стартирай)(?:\s+ми)?\s+)?таймер(?:\s+(?:за|от))?\s+(?P<d>.+)",
               re.IGNORECASE),
    re.compile(r"засечи(?:\s+ми)?\s+(?P<d>.+)", re.IGNORECASE),
)
_CLAUDE = r"(?:claude|клод|клауд)"
_ASK_CLAUDE_RE = re.compile(rf"(?:попитай|питай|запитай)\s+{_CLAUDE}[\s,:]+(?P<q>.+)", re.IGNORECASE)
_TELL_CLAUDE_RE = re.compile(
    rf"(?:напиши|пиши|прати|изпрати|кажи)\s+(?:на\s+)?{_CLAUDE}[\s,:]+(?:че\s+)?(?P<q>.+)", re.IGNORECASE)
# Списъци (пазарски и др.): „добави мляко и хляб в пазарския списък“, „какво има в списъка“.
_LIST = r"(?:(?P<list>[\w-]+?)(?:ия|ия ми|ият)?\s+)?списъ(?:к|ка)(?:\s+(?:ми|за\s+(?P<for>[\w\s]+)))?"
_LIST_ADD_RE = re.compile(rf"(?:добави|сложи|запиши|пиши)(?:\s+ми)?\s+(?P<items>.+?)\s+(?:в|във|към)\s+{_LIST}",
                          re.IGNORECASE)
_LIST_REMOVE_RE = re.compile(rf"(?:махни|изтрий|извади|задраскай)(?:\s+ми)?\s+(?P<items>.+?)\s+от\s+{_LIST}",
                             re.IGNORECASE)
_LIST_SHOW_RE = re.compile(rf"(?:какво има в|прочети(?:\s+ми)?|покажи(?:\s+ми)?|кажи ми)\s+{_LIST}", re.IGNORECASE)
_GAMES_RE = re.compile(r"(?:какви|кои) игри имам|покажи (?:ми )?игрите(?: ми)?|(?:списък|списъка) (?:с|на) игрите",
                       re.IGNORECASE)
_CITY_TIME_RE = re.compile(r"(?:колко е часът|колко е часа|колко часа е|кое време е|какъв час е)\s+(?:в|във)\s+"
                           r"(?P<city>[^?!.,]+)", re.IGNORECASE)
# Команди за компютъра: (израз, умение, аргументи). {n} в аргументите = числото от фразата.
_SYSTEM_COMMANDS = [
    (r"(?:намали|намалете|свали|свалете)(?: ми)? звука(?: с (?P<n>\d+))?(?: процента| %)?|по-тихо", "change_volume",
     {"amount": "-{n}"}),
    (r"(?:усили|усилете|увеличи|увеличете|дай|вдигни)(?: ми)? звука(?: с (?P<n>\d+))?(?: процента| %)?|по-силно|"
     r"по-високо", "change_volume", {"amount": "{n}"}),
    (r"(?:сложи|направи|пусни)?(?: ми)? ?звука? (?:на )?(?P<n>\d+)(?: процента| %)?", "set_volume", {"level": "{n}"}),
    (r"заглуши(?: звука)?|спри звука|без звук|mute", "mute_sound", {"mute": True}),
    (r"(?:пусни|върни|включи) звука", "mute_sound", {"mute": False}),
    (r"пауза|спри|спри (?:музиката|песента|видеото|клипа)|паузирай", "media_control", {"action": "pause"}),
    (r"(?:продължи|пусни) (?:музиката|песента|видеото)", "media_control", {"action": "play"}),
    (r"следващ(?:ата|ия)?(?: песен| клип| видео)?|пусни следващата(?: песен)?", "media_control", {"action": "next"}),
    (r"предишн(?:ата|ия)?(?: песен| клип| видео)?|пусни предишната(?: песен)?", "media_control", {"action": "previous"}),
    (r"заключи (?:компютъра|екрана)", "power_action", {"action": "lock"}),
    (r"(?:изключи|спри) компютъра(?: след (?P<n>\d+) минути)?", "power_action", {"action": "shutdown", "minutes": "{n}"}),
    (r"рестартирай компютъра(?: след (?P<n>\d+) минути)?", "power_action", {"action": "restart", "minutes": "{n}"}),
    (r"приспи компютъра", "power_action", {"action": "sleep"}),
    (r"(?:отмени|откажи|спри) (?:изключването|рестартирането|рестарта)", "power_action", {"action": "cancel"}),
    (r"(?:направи|снимай)(?: ми)? (?:снимка на екрана|скрийншот)|скрийншот", "take_screenshot", {}),
    (r"какво (?:има|виждаш|се вижда) на екрана|погледни (?:екрана|монитора)|прочети (?:ми )?екрана|"
     r"какво виждаш", "look_at_screen", {"question": "{text}"}),
    (r"(?:как е|провери|състояние на) (?:компютъра|системата)(?: ми)?|как е компютърът(?: ми)?", "system_status", {}),
    (r"затвори (?:ми )?(?:програмата |играта )?(?P<name>(?!се\b)[\w .+-]+)", "close_program", {"name": "{name}"}),
]
_SYSTEM_RES = [(re.compile(pattern, re.IGNORECASE), tool, args) for pattern, tool, args in _SYSTEM_COMMANDS]


def _system_command(plain: str) -> Reflex | None:
    for pattern, tool, template in _SYSTEM_RES:
        match = pattern.fullmatch(plain)
        if not match:
            continue
        groups = match.groupdict()
        number = groups.get("n")
        arguments = {}
        for key, value in template.items():
            if not isinstance(value, str):
                arguments[key] = value
            elif "{n}" in value:  # по подразбиране: звук ±10, изключване след 0 минути
                default = "10" if key == "amount" else "0"
                arguments[key] = int(value.replace("{n}", number or default))
            else:
                arguments[key] = value.replace("{text}", plain).replace("{name}", (groups.get("name") or "").strip())
        return Reflex(tool=tool, arguments=arguments)
    return None


_GOOGLE_SETUP_RE = re.compile(
    r"(?:свържи|свържете|настрой|настройте|включи|добави)(?:\s+(?:се|ми))?(?:\s+(?:с|със|към))?\s+"
    r"(?:гугъл|google|gmail|джимейл)(?:\s+\w+)?", re.IGNORECASE)


# Тест режим (jarvis/self_test.py): Орион сам се проверява и поправя.
_TEST = r"(?:тест(?:ов(?:ия|ият)?)?\s+режим(?:а|ът)?|самопроверка(?:та)?|самотест(?:а|ът)?|тестовете|теста|тестването)"
_TEST_OFF_RE = re.compile(rf"(?:изключи|изключете|спри|спрете|прекрати|прекратете)(?:\s+ми)?\s+{_TEST}(?:[\s,]+моля)?",
                          re.IGNORECASE)
_TEST_REPORT_RE = re.compile(
    rf"(?:как мина|как минаха|какво (?:показа|показаха|откри|намери)|какъв е резултатът от|кажи ми резултата от|"
    rf"резултат(?:ът|ите)? от)\s+{_TEST}", re.IGNORECASE)
_TEST_ON_RE = re.compile(
    rf"(?:(?:включи|включете|пусни|пуснете|стартирай|започни|активирай)(?:\s+ми)?\s+{_TEST}|тест(?:ов)?\s+режим|"
    rf"тествай се|тествайте се|самопровери се|провери се сам|провери сам себе си|"
    rf"направи(?:\s+си)?\s+(?:тест|самопроверка|самотест))(?:[\s,]+моля)?", re.IGNORECASE)


_REEL_WORDS = r"рийл|reel|шорт|short|изреж|клипчета|клипове|откъс"
_REELS = r"(?:рийлове(?:те)?|рийла|рийлът|шортс(?:овете)?|клипчетата)"
_REELS_STATUS_RE = re.compile(
    rf"(?:готови ли са|готов ли е|как върв(?:и|ят)|докъде (?:са|си стигнал|стигна)(?: с)?|какво става с)\s+"
    rf"(?:ми\s+)?{_REELS}", re.IGNORECASE)
_REELS_SHOW_RE = re.compile(rf"(?:покажи|отвори)(?:\s+ми)?\s+(?:папката\s+с\s+)?{_REELS}", re.IGNORECASE)
_REELS_MOMENTS_RE = re.compile(r"най-(?:интересн|гледан|хубав|смешн|добр)\w*\s+(?:моменти|места|части)", re.IGNORECASE)
_COUNT_WORDS = {"един": 1, "една": 1, "два": 2, "две": 2, "три": 3, "четири": 4, "пет": 5, "шест": 6,
                "седем": 7, "осем": 8, "девет": 9, "десет": 10}


def _youtube_link(url: str, rest: str) -> Reflex:
    """Линк от YouTube в чата. Само линк или „направи рийлове“ -> рийлове; „анализирай“ -> анализ;
    „пусни/гледай“ -> отваря клипа."""
    reels_wanted = re.search(_REEL_WORDS, rest)
    if re.search(r"анализ|кое е най|кои са най|кои моменти", rest) and not reels_wanted:
        return Reflex(tool="analyze_youtube_video", arguments={"url": url})
    if re.search(r"\b(пусни|гледай|отвори|покажи)\b", rest) and not reels_wanted:
        return Reflex("Отварям клипа, сър.", "open_website", {"url": url})
    arguments: dict = {"url": url}
    count = re.search(rf"(\d+|{'|'.join(_COUNT_WORDS)})\s*(?:{_REEL_WORDS}|видеа|клипа)", rest)
    if count:
        arguments["count"] = int(count[1]) if count[1].isdigit() else _COUNT_WORDS[count[1]]
    seconds = re.search(r"(\d+)\s*(?:секунд|сек\b|s\b)", rest)
    minutes = re.search(r"(\d+|една|две|три)?\s*минут", rest)
    if seconds:
        arguments["seconds"] = int(seconds[1])
    elif minutes:
        arguments["seconds"] = 60 * (int(minutes[1]) if (minutes[1] or "").isdigit() else _COUNT_WORDS.get(minutes[1], 1))
    if re.search(r"без субтитри|без надписи", rest):
        arguments["subtitles"] = False
    return Reflex(tool="make_youtube_reels", arguments=arguments)


def _plain(text: str) -> str:
    """Фразата без името („Орион“), „моля“ и препинателни знаци по краищата."""
    text = _WAKE_RE.sub(" ", text)
    text = re.sub(r"^\s*(?:моля(?:\s+те)?|ей|хей)[\s,]+", "", text, flags=re.IGNORECASE)
    return text.strip(" ,.!?")


def _words(text: str) -> list[str]:
    return re.findall(r"[\w\-.:/]+", text.replace("ё", "е").replace("Ё", "Е"))


def _clock_answer(words: list[str], now: datetime) -> str | None:
    meaningful = [w for w in words if w not in _FILLER]
    topics = {w for w in meaningful if w in _TIME | _DATE | _DAY}
    if not topics or any(w not in _GLUE | _TIME | _DATE | _DAY for w in meaningful):
        return None
    wants_time = bool(topics & _TIME)
    wants_date = bool(topics & _DATE)
    if wants_time and (wants_date or topics & _DAY):
        return f"Днес е {clock.date_text(now)}, а часът е {clock.time_text(now)}, сър."
    if wants_time:
        return f"Часът е {clock.time_text(now)}, сър."
    if wants_date:
        return f"Днес е {clock.date_text(now)}, сър."
    return f"Днес е {clock.weekday(now)}, {now.day} {clock.MONTHS[now.month - 1]}, сър."


def respond(text: str, now: datetime | None = None) -> Reflex | None:
    """Рефлекс за фразата или None (тогава отговаря езиковият модел)."""
    now = now or datetime.now()
    words = _words(text)
    lower = [w.lower() for w in words]
    if not words:
        return None

    answer = _clock_answer(lower, now)
    if answer:
        return Reflex(answer)

    if " ".join(w for w in lower if w not in _FILLER) in _CLOSE:
        return Reflex("Довиждане, сър. Ще бъда тук, когато ме потърсите.", action="close")

    url = google.URL_RE.search(text)
    if url:  # Сър е поставил адреса на моста към Google.
        return Reflex(action="google_connect", arguments={"url": url.group(0)})
    plain = _plain(text)
    if _GOOGLE_SETUP_RE.fullmatch(plain):
        return Reflex(action="google_setup")
    for pattern, action in ((_TEST_OFF_RE, "test_off"), (_TEST_REPORT_RE, "test_report"), (_TEST_ON_RE, "test_on")):
        if pattern.fullmatch(plain):
            return Reflex(action=action)
    video = reels.find_url(text)
    if video:  # линк от YouTube -> рийлове (или анализ / пускане, ако сър е казал това)
        return _youtube_link(video, reels.YOUTUBE_RE.sub(" ", plain).lower())
    if _REELS_STATUS_RE.fullmatch(plain):
        return Reflex(tool="reels_status", arguments={})
    if _REELS_SHOW_RE.fullmatch(plain):
        return Reflex(tool="show_reels", arguments={})
    if reels.last_url and _REELS_MOMENTS_RE.search(plain):  # „най-интересните моменти в клипа“ — последния
        return Reflex(tool="analyze_youtube_video", arguments={"url": ""})

    match = _ASK_CLAUDE_RE.fullmatch(plain)
    if match:
        return Reflex(tool="ask_claude", arguments={"question": match["q"].strip()})
    match = _TELL_CLAUDE_RE.fullmatch(plain)
    if match:
        return Reflex(tool="send_to_claude_app", arguments={"prompt": match["q"].strip()})
    if _GAMES_RE.fullmatch(plain):
        return Reflex(tool="list_games", arguments={})
    for pattern, tool in ((_LIST_ADD_RE, "add_to_list"), (_LIST_REMOVE_RE, "remove_from_list"),
                          (_LIST_SHOW_RE, "show_list")):
        match = pattern.fullmatch(plain)
        if match:
            name = (match["for"] or match["list"] or "пазарски").strip()
            arguments = {"list_name": name}
            if "items" in match.groupdict() and match["items"]:
                arguments["items"] = match["items"].strip()
            return Reflex(tool=tool, arguments=arguments)

    match = _CITY_TIME_RE.fullmatch(plain)
    if match and clock.zone_for(match["city"]):
        there = datetime.now(clock.zone_for(match["city"]))
        return Reflex(f"{clock.in_place(match['city'], capital=True)} часът е {clock.time_text(there)}, сър.")

    system = _system_command(plain.lower())
    if system:
        return system

    for pattern in _TIMER_RES:
        match = pattern.fullmatch(plain)
        if match and when.parse_in(match["d"]):
            return Reflex(tool="set_timer", arguments={"duration": match["d"]})

    for pattern in _SEARCH_RES:
        match = pattern.fullmatch(plain)
        if match:
            site, query = _SEARCH_SITES[match["site"].lower()], match["query"].strip()
            if site == "youtube" and re.match(r"пусн", plain, re.IGNORECASE):  # „пусни ми X в YouTube“
                return Reflex(tool="play_on_youtube", arguments={"query": query})
            url = (f"https://www.youtube.com/results?search_query={quote_plus(query)}" if site == "youtube"
                   else f"https://www.google.com/search?q={quote_plus(query)}")
            where = "YouTube" if site == "youtube" else "Google"
            return Reflex(f"Търся „{query}“ в {where}, сър.", "open_website", {"url": url})

    # Командите се разпознават без думите-пълнеж, но „ми“, „е“ и „в“ са част от изразите.
    # Главните букви остават — „YouTube“ се показва така, както е казано.
    command = " ".join(w for w in words if w.lower() not in _FILLER - {"ми", "е", "в"})

    match = _OPEN_RE.fullmatch(command)
    if match:
        target = match.group("target").strip()
        site = apps.find_site(target)
        program = None if site else apps.find_program(target)
        if program:
            verb = "Пускам" if program[1] == "game" else "Отварям"
            return Reflex(f"{verb} {program[0]}, сър.", "open_program", {"name": target})
        if site:
            return Reflex(f"Отварям {target}, сър.", "open_website", {"url": target})
        return None  # Непозната програма — моделът ще реши (може да създаде умение).

    match = _WEATHER_RE.fullmatch(command)
    if match:
        city = (match.group("city") or "").strip()
        return Reflex(tool="get_weather", arguments={"city": city} if city else {})
    return None


def weather_answer(result: str) -> str:
    """Превръща „София: 18°C (усеща се като 17°C), облачно, вятър…“ в изречение за глас."""
    match = re.match(r"(?P<city>.+?): (?P<t>-?\d+)°C \(усеща се като (?P<f>-?\d+)°C\), (?P<d>.+?), "
                     r"вятър (?P<w>\d+) км/ч", result)
    if not match:
        return result
    t, f = int(match["t"]), int(match["f"])
    degrees = lambda n: "1 градус" if abs(n) == 1 else f"{n} градуса"  # noqa: E731
    feels = f", усеща се като {degrees(f)}" if abs(t - f) >= 2 else ""
    return (f"{clock.in_place(match['city'], capital=True)} е {degrees(t)}{feels}, {match['d'].lower()}, "
            f"вятър {match['w']} километра в час, сър.")
