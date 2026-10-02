"""
Reflexes — instant, always-correct answers to the most common commands, without the language model.

Small local models sometimes get the day of the week wrong or “say” they opened
a program without doing it. So the time, the date, opening programs and websites,
Google/YouTube searches, the weather, timers, connecting Google and closing
Orion are recognised here with simple rules. Anything that does not match exactly goes to the model.
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
    tool: str | None = None        # a skill to run (goes through the registry)
    arguments: dict | None = None
    # An app action: "close" (shut down), "google_setup", "google_connect".
    action: str | None = None

    @property
    def arguments_json(self) -> str:
        return json.dumps(self.arguments or {}, ensure_ascii=False)


# Words that do not change the meaning of the question: „Орион, кажи ми моля колко е часът сега?“
_FILLER = set(config.WAKE_WORDS) | {
    "моля", "те", "ей", "хей", "бе", "де",
    "братле", "брат", "сър", "кажи", "кажете", "кажеш", "ми", "можеш", "можете", "може", "ли", "да",
    "би", "казал", "искам", "знам", "сега", "в", "момента", "точно", "точния", "точният", "точната",
    "ако", "обичаш", "обичате", "бързо", "веднага", "я", "а", "добре",
}
# A time/date/day question: all words are from these + at least one topic. Otherwise („колко е часът
# в Ню Йорк“, „кой ден беше вчера“) the question goes to the model.
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
# Lists (shopping etc.): „добави мляко и хляб в пазарския списък“, „какво има в списъка“.
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
# Computer commands: (pattern, skill, arguments). {n} in the arguments = the number from the phrase.
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
    (r"(?:(?:сложи|пусни|дай|давай)(?: ми)? )?следващ(?:а|ата|ия|ото)?(?: песен| клип| видео)?", "media_control",
     {"action": "next"}),
    (r"(?:(?:сложи|пусни|дай|върни)(?: ми)? )?предишн(?:а|ата|ия|ото)?(?: песен| клип| видео)?", "media_control",
     {"action": "previous"}),
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

# Everyday requests the small model often answers „from its head“ (it „flips the coin“ itself, translates or
# guesses distances without the skill) — test mode showed it. Here they always go to the right skill.
# (pattern, skill, function: match -> arguments)
_LANGS = (r"английски|немски|френски|руски|испански|италиански|турски|гръцки|български|японски|китайски|полски|"
          r"румънски|сръбски|португалски|арабски|нидерландски|украински")
_NUMBER = rf"\d+|{'|'.join(['един', 'една', 'два', 'две', 'три', 'четири', 'пет', 'шест'])}"


def _quoted(text: str) -> str:
    return text.strip().strip("„“\"'«»").strip()


def _int(text: str | None, default: int | None = None) -> int | None:
    if not text:
        return default
    return int(text) if text.isdigit() else {"един": 1, "една": 1, "два": 2, "две": 2, "три": 3, "четири": 4,
                                             "пет": 5, "шест": 6}.get(text.lower(), default)


def _drop_none(arguments: dict) -> dict:
    return {k: v for k, v in arguments.items() if v not in (None, "")}


_EVERYDAY = [
    (r"(?:хвърли|хвърлиш|метни)(?: ми)?(?: една)? монета(?:та)?|ези или тура|тура или ези", "flip_coin", lambda m: {}),
    (rf"(?:хвърли|хвърлиш|метни)(?: ми)?(?: (?P<n>{_NUMBER}))? (?:зар|зара|зарове|зарчета)(?: сега)?", "roll_dice",
     lambda m: {"count": _int(m["n"], 1)}),
    (r"(?:(?:измисли|избери|дай|кажи|генерирай)(?: ми)? )?(?:(?:едно|случайно|произволно) )*число (?:от|между) "
     r"(?P<a>-?\d+) (?:до|и) (?P<b>-?\d+)", "random_number", lambda m: {"minimum": int(m["a"]), "maximum": int(m["b"])}),
    (r"избери(?: ми)?(?: (?:между|от))? (?P<options>[^?]+?(?:,| или )[^?]+)|"
     r"какво да (?:избера|изберем|ям|хапна|хапнем|гледам|гледаме)[:,]? (?P<options2>[^?]+?(?:,| или )[^?]+)",
     "pick_random", lambda m: {"options": m["options"] or m["options2"]}),
    (rf"преведи(?: ми)?(?: на)? (?P<lang>{_LANGS})(?: език)?[:,]? (?P<text>.+)|"
     rf"преведи(?: ми)? (?P<text2>.+?) на (?P<lang2>{_LANGS})(?: език)?|"
     rf"как (?:е|се казва|ще бъде) (?P<text3>.+?) на (?P<lang3>{_LANGS})|как е на (?P<lang4>{_LANGS}) (?P<text4>.+)",
     "translate_text", lambda m: {"text": _quoted(m["text"] or m["text2"] or m["text3"] or m["text4"]),
                                  "to_language": (m["lang"] or m["lang2"] or m["lang3"] or m["lang4"]).lower()}),
    (r"(?:колко (?:километра|км|далеч)(?: е| са)?|какво е разстоянието|разстояние(?:то)?) (?:от|между) "
     r"(?P<a>[^?,]+?) (?:до|и) (?P<b>[^?,]+)", "distance_between",
     lambda m: {"from_city": m["a"].strip(), "to_city": m["b"].strip()}),
    (r"(?:покажи|отвори)(?: ми)? (?:работния плот|десктопа)|(?:скрий|минимизирай|свий)(?: всички)? "
     r"(?:прозорци(?:те)?|всичко)", "minimize_all_windows", lambda m: {}),
    (r"(?:прочети|кажи|покажи)(?: ми)? (?:какво (?:съм|сме|е) копира\w*|копирания текст|клипборда)(?: в момента)?|"
     r"какво (?:съм|сме) копира\w*(?: в момента)?|копирах (?:текст|нещо),? прочети го", "read_clipboard", lambda m: {}),
    (r"(?:кога е |кой е )?следващ(?:ият|ия) (?:официален |неработен )?(?:празник|почивен ден)", "next_holiday",
     lambda m: {}),
    (r"(?:в колко часа|кога)(?: е)? (?:залязва|изгрява|залезът|изгревът|залеза|изгрева)(?: слънцето)?(?: днес)?"
     r"(?: (?:в|във) (?P<city>[^?]+?))?(?: днес)?|(?:залез|изгрев)(?:ът)?(?: днес)?(?: (?:в|във) (?P<city2>[^?]+))?",
     "sunrise_sunset", lambda m: _drop_none({"city": (m["city"] or m["city2"] or "").strip()})),
    (r"(?:генерирай|направи|измисли|дай)(?: ми)?(?: (?:една|нова|силна|сигурна|случайна))* парола"
     r"(?: (?:от|с) (?P<n>\d+) (?:символа|знака|букви))?", "generate_password",
     lambda m: _drop_none({"length": _int(m["n"])})),
    (r"(?:(?:пусни|започни|включи|направи|стартирай)(?: ми)? )?помодоро(?: (?:от|за) (?P<n>\d+) минути)?(?: за работа)?",
     "pomodoro", lambda m: _drop_none({"minutes": _int(m["n"])})),
    (r"ще (?:вали|завали|има дъжд)(?: ли)?(?: (?P<day>днес|утре|вдругиден|довечера))?(?: (?:в|във) (?P<city>[^?]+?))?"
     r"(?: (?P<day2>днес|утре|вдругиден|довечера))?(?: ли)?", "will_it_rain",
     lambda m: _drop_none({"city": (m["city"] or "").strip(), "day": m["day"] or m["day2"] or "днес"})),
    (r"(?:какъв е |какво е |кое е )?(?:индекс(?:ът|а)? на страха(?: и алчността)?|(?:текущото )?ниво(?:то)? на страха "
     r"(?:в|на) крипто\w*(?: пазара)?)(?: сега)?", "crypto_fear_greed", lambda m: {}),
    (r"(?:какви|кои) (?:напомняния|аларми|таймери) (?:имам|има|са пуснати|чакат)|(?:покажи|прочети)(?: ми)? "
     r"напомнянията(?: ми)?", "list_reminders", lambda m: {}),
    (r"(?:какви|кои) (?:ценови )?(?:известия|алерти|аларми за цени)(?: за цени)? (?:имам|има|са активни|са пуснати)|"
     r"(?:покажи|кажи)(?: ми)? (?:кой|кои) (?:ценови )?(?:алерт|алерти|известия) (?:е|са) актив\w+",
     "list_price_alerts", lambda m: {}),
]
_EVERYDAY_RES = [(re.compile(pattern, re.IGNORECASE), tool, build) for pattern, tool, build in _EVERYDAY]


_POLITE_RE = re.compile(r"^(?:(?:може ли|можеш ли|би ли|ще можеш ли)(?: да)?|(?:кажи|казвай|кажете)(?: ми)?|"
                        r"искам да|хайде)\s+", re.IGNORECASE)


def _everyday(plain: str) -> Reflex | None:
    plain = _POLITE_RE.sub("", plain)  # „може ли да хвърлиш зар“ = „хвърли зар“
    for pattern, tool, build in _EVERYDAY_RES:
        match = pattern.fullmatch(plain)
        if match:
            return Reflex(tool=tool, arguments=build(match))
    return None


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
            elif "{n}" in value:  # defaults: volume ±10, shutdown after 0 minutes
                default = "10" if key == "amount" else "0"
                arguments[key] = int(value.replace("{n}", number or default))
            else:
                arguments[key] = value.replace("{text}", plain).replace("{name}", (groups.get("name") or "").strip())
        return Reflex(tool=tool, arguments=arguments)
    return None


_GOOGLE_SETUP_RE = re.compile(
    r"(?:свържи|свържете|настрой|настройте|включи|добави)(?:\s+(?:се|ми))?(?:\s+(?:с|със|към))?\s+"
    r"(?:гугъл|google|gmail|джимейл)(?:\s+\w+)?", re.IGNORECASE)


# Test mode (orion/self_test.py): Orion checks and repairs itself.
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
# „намери видеа без авторски права за космоса“ — free (Creative Commons) videos for reels
_FREE_WORDS = (r"без\s+(?:авторски\s+права|копирайт\w*|права)|свободн\w*(?:\s+от\s+авторски\s+права)?|"
               r"creative\s+commons|криейтив\s+комънс")
_FIND_FREE_RE = re.compile(
    rf"(?:намери|потърси|търси|дай|покажи)(?:\s+ми)?(?:\s+(?P<n>\d+|{'|'.join(_COUNT_WORDS)}))?"
    rf"(?:\s+(?:{_FREE_WORDS}))?\s+(?:видеа|видео|видеоклипове|клипове|клипчета|клипа)(?:\s+(?:{_FREE_WORDS}))?"
    rf"(?:\s+(?:за|на тема|относно))?\s+(?P<topic>.+)", re.IGNORECASE)
# „направи рийлове от номер 2“ / „изрежи 3 рийла от второто“ — from the last search for free videos
_REELS_FROM_FOUND_RE = re.compile(
    rf"(?:направи|изрежи)(?:\s+ми)?(?:\s+(?P<n>\d+|{'|'.join(_COUNT_WORDS)}))?\s+(?:рийл\w*|шорт\w*|клипчета)\s+"
    rf"(?:от\s+)?(?:(?:клип|видео)\w*\s+)?(?P<pick>(?:номер\s*|№\s*)?\d{{1,2}}|(?:номер\s+)?"
    rf"(?:първ|втор|трет|четвърт|пет|шест|седм|осм|девет|десет)\w*)", re.IGNORECASE)


# „Рийл“ / „Real“ (the speech recogniser often writes it that way) — Orion picks a free clip by itself.
_REEL_WORD = r"(?:рийл|рийла|рийлове|рийлс|риъл|рил|реал|reels?|real)"
_AUTO_REEL_RE = re.compile(
    rf"(?:(?:направи|дай|искам|хайде|пусни|изрежи)(?:\s+ми)?\s+)?"
    rf"(?:(?P<n>\d+|{'|'.join(_COUNT_WORDS)}|нов|още\s+един)\s+)?{_REEL_WORD}"
    rf"(?:\s+(?:сам|ти|по твой избор|избери ти|ти избери|избери сам))?"
    rf"(?:\s+(?:за|на тема)\s+(?P<topic>.+))?", re.IGNORECASE)
# A longer request where sir leaves the choice to Orion: „искам да направиш един reel, като вземеш видеата,
# които ти решиш“. Google sometimes hears „рийл“ as „Рио“ — accepted only right after „направи“.
_AUTO_REEL_ASK_RE = re.compile(
    rf"(?:\b(?:направи\w*|изрежи\w*|дай)\b.*?\b{_REEL_WORD}\b|\bнаправи\w*(?:\s+ми)?(?:\s+(?:един|една|нов))?\s+рио\b)"
    r".*\b(?:(?:ти|сам)(?:\s+си)?\s+(?:решиш|ришиш|избереш|прецениш|реши|избери|прецени|намериш|намери)|"
    r"по\s+твой\s+избор|по\s+твоя\s+преценка|(?:които|който|каквото|което)\s+(?:ти\s+)?(?:искаш|решиш|избереш|прецениш))\b",
    re.IGNORECASE)
# „направи рийлове от този клип“ — the last clip (after a link or an analysis)
_REELS_FROM_LAST_RE = re.compile(
    rf"(?:направи|изрежи)(?:\s+ми)?(?:\s+(?P<n>\d+|{'|'.join(_COUNT_WORDS)}))?\s+{_REEL_WORD}\s+от\s+"
    rf"(?:този|последния|същия|предишния|него)(?:\s+(?:клип|видео)\w*)?", re.IGNORECASE)


def _count(word: str | None) -> int | None:
    if not word:
        return None
    return int(word) if word.isdigit() else _COUNT_WORDS.get(word.lower())


def _youtube_link(url: str, rest: str) -> Reflex:
    """A YouTube link in the chat. Just a link or „направи рийлове“ -> reels; „анализирай“ -> analysis;
    „пусни/гледай“ (play/watch) -> opens the video."""
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
    if re.search(r"без (?:субтитри|надписи|текст)", rest):
        arguments["subtitles"] = False
    elif re.search(r"(?:със|с) (?:субтитри|надписи|текст)", rest):
        arguments["subtitles"] = True
    return Reflex(tool="make_youtube_reels", arguments=arguments)


def _plain(text: str) -> str:
    """The phrase without the name („Орион“), „моля“ (please) and punctuation at the ends."""
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
    """A reflex for the phrase, or None (then the language model answers)."""
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
    if url:  # Sir pasted the address of the Google bridge.
        return Reflex(action="google_connect", arguments={"url": url.group(0)})
    plain = _plain(text)
    if _GOOGLE_SETUP_RE.fullmatch(plain):
        return Reflex(action="google_setup")
    for pattern, action in ((_TEST_OFF_RE, "test_off"), (_TEST_REPORT_RE, "test_report"), (_TEST_ON_RE, "test_on")):
        if pattern.fullmatch(plain):
            return Reflex(action=action)
    video = reels.find_url(text)
    if video:  # a YouTube link -> reels (or analysis / playing, if sir said so)
        return _youtube_link(video, reels.YOUTUBE_RE.sub(" ", plain).lower())
    if _REELS_STATUS_RE.fullmatch(plain):
        return Reflex(tool="reels_status", arguments={})
    if _REELS_SHOW_RE.fullmatch(plain):
        return Reflex(tool="show_reels", arguments={})
    if reels.last_url and _REELS_MOMENTS_RE.search(plain):  # „най-интересните моменти в клипа“ (the most interesting moments) — of the last video
        return Reflex(tool="analyze_youtube_video", arguments={"url": ""})
    match = _FIND_FREE_RE.fullmatch(plain)
    if match and re.search(_FREE_WORDS, plain[:match.start("topic")], re.IGNORECASE):
        topic = re.sub(r"^(?:рийл\w*|шорт\w*)\s+(?:за|на тема)\s+", "", match["topic"].strip(), flags=re.IGNORECASE)
        arguments = {"topic": topic}
        if _count(match["n"]):
            arguments["count"] = _count(match["n"])
        return Reflex(tool="find_free_videos", arguments=arguments)
    match = _REELS_FROM_FOUND_RE.fullmatch(plain)
    if match and reels.pick_found(match["pick"]):
        arguments = {"url": reels.pick_found(match["pick"])}
        if _count(match["n"]):
            arguments["count"] = _count(match["n"])
        return Reflex(tool="make_youtube_reels", arguments=arguments)
    match = _REELS_FROM_LAST_RE.fullmatch(plain)
    if match and reels.last_url:
        arguments = {"url": reels.last_url}
        if _count(match["n"]):
            arguments["count"] = _count(match["n"])
        return Reflex(tool="make_youtube_reels", arguments=arguments)
    if _AUTO_REEL_ASK_RE.search(plain):  # „…един рийл от видеа, които ти решиш“ — Orion chooses
        count = re.search(rf"\b(\d+|{'|'.join(_COUNT_WORDS)})\s+{_REEL_WORD}", plain, re.IGNORECASE)
        return Reflex(tool="auto_reels", arguments={"topic": "", **({"count": _count(count[1])} if count else {})})
    match = _AUTO_REEL_RE.fullmatch(plain)
    if match:  # „Рийл“ — Orion chooses the clip
        arguments = {"topic": (match["topic"] or "").strip()}
        if _count(match["n"]):
            arguments["count"] = _count(match["n"])
        return Reflex(tool="auto_reels", arguments=arguments)

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
    everyday = _everyday(plain)
    if everyday:
        return everyday

    for pattern in _TIMER_RES:
        match = pattern.fullmatch(plain)
        if match and when.parse_in(match["d"]):
            return Reflex(tool="set_timer", arguments={"duration": match["d"]})

    for pattern in _SEARCH_RES:
        match = pattern.fullmatch(plain)
        if match:
            site, query = _SEARCH_SITES[match["site"].lower()], match["query"].strip()
            if site == "youtube" and re.match(r"пусн", plain, re.IGNORECASE):  # „пусни ми X в YouTube“ (play X on YouTube)
                return Reflex(tool="play_on_youtube", arguments={"query": query})
            url = (f"https://www.youtube.com/results?search_query={quote_plus(query)}" if site == "youtube"
                   else f"https://www.google.com/search?q={quote_plus(query)}")
            where = "YouTube" if site == "youtube" else "Google"
            return Reflex(f"Търся „{query}“ в {where}, сър.", "open_website", {"url": url})

    # Commands are recognised without filler words, but „ми“, „е“ and „в“ are part of the patterns.
    # Capitals are kept — „YouTube“ is shown as it was said.
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
        return None  # Unknown program — the model decides (it may create a skill).

    match = _WEATHER_RE.fullmatch(command)
    if match:
        city = (match.group("city") or "").strip()
        return Reflex(tool="get_weather", arguments={"city": city} if city else {})
    return None


def weather_answer(result: str) -> str:
    """Turns „София: 18°C (усеща се като 17°C), облачно, вятър…“ into a sentence to speak."""
    match = re.match(r"(?P<city>.+?): (?P<t>-?\d+)°C \(усеща се като (?P<f>-?\d+)°C\), (?P<d>.+?), "
                     r"вятър (?P<w>\d+) км/ч", result)
    if not match:
        return result
    t, f = int(match["t"]), int(match["f"])
    degrees = lambda n: "1 градус" if abs(n) == 1 else f"{n} градуса"  # noqa: E731
    feels = f", усеща се като {degrees(f)}" if abs(t - f) >= 2 else ""
    return (f"{clock.in_place(match['city'], capital=True)} е {degrees(t)}{feels}, {match['d'].lower()}, "
            f"вятър {match['w']} километра в час, сър.")
