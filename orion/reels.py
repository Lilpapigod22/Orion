"""
Рийлове от YouTube — Орион намира най-интересните моменти в клип и ги изрязва като вертикални
видеа за YouTube Shorts: 9:16, кадрирани по лицата, само картината и звукът (без текст върху видеото),
изравнен звук, точно съвпадение на звука и картината, предложено заглавие, хаштагове и корица.

Само свободни клипове (config.REEL_FREE_ONLY): рийлове се правят само от клипове, които авторът е пуснал
с лиценз Creative Commons — Признание (CC BY), и то ако няма признаци, че клипът е качен от чужд канал
(„правата не са мои“ в описанието, чужда марка в заглавието, музика, филми, компилации, мачове).
Търсенето на такива клипове по тема е в find_free; в описанието на рийловете има готов ред с автора.
„Рийл“ (start_auto): Орион сам избира такъв клип с най-голям шанс за много гледания и прави рийловете.

Как избира моментите:
  1. Сигнали — всяка секунда от клипа получава оценка от:
       - „Най-гледани моменти“ на YouTube (heatmap): къде зрителите превъртат и гледат отново;
       - коментарите с час („3:45 тук умрях от смях“), с тежест според харесванията им;
       - силата на звука (смях, викове, музика) — когато YouTube няма данни за гледанията (нов или
         малък клип): основният сигнал, ако няма и коментари с час, иначе помощен (по-слаб от тях).
     Най-силните места стават кандидати (с два повече, отколкото рийлове са поискани).
  2. Редактор — Орион чете какво се казва в кандидатите (субтитрите на YouTube или Whisper) и
     езиковият модел избира самостоятелен откъс: започва с „кука“, свършва с поанта, реже се по
     изречения (не по средата на дума) и получава оценка 1–10. Най-добрите стават рийлове.
Как ги реже:
  - от YouTube се теглят само нужните откъси (ffmpeg чете направо от адреса, който дава yt-dlp);
  - при клип с хора кадърът е на цял екран и следва лицето във всяка сцена (OpenCV, YuNet); иначе
    (игри, анимация) — целият кадър върху замъглен фон; черните ленти се махат;
  - звукът и картината се режат по часовете на YouTube, затова съвпадат точно;
  - звук до -14 LUFS, кодиране на видеокартата; корица за всеки рийл;
  - субтитри дума по дума и заглавие върху видеото — само ако сър ги поиска (config.REEL_SUBTITLES).
Всичко отива в config.REELS_DIR (на D:). Работата е във фонова нишка: Орион казва „започнах“
веднага и съобщава, когато е готов.
"""
import json
import math
import random
import re
import shutil
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import config

YOUTUBE_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?\S*?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"[\w-]{11}[^\s,;!?„“\"']*", re.IGNORECASE)
TIMESTAMP_RE = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])")
WIDTH, HEIGHT = 1080, 1920
MARGIN = 3.0            # секунди в повече при тегленето — за точно рязане
MIN_FREE_GB = 2
AUDIO_MAX_SECONDS = 2 * 3600   # по-дълги клипове без други сигнали не се анализират по звука
EXTRA_CANDIDATES = 2    # колко кандидата повече от поисканите рийлове оценява редакторът
SAMPLE_FPS, SAMPLE_WIDTH = 3, 640   # за търсенето на лица (и малката камера на стриймър)
_CREATE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0 Safari/537.36"}

# Задават се от приложението: notify — казва на глас, progress — пише в журнала,
# state — индикаторът горе в прозореца ({"active": bool, "text": str}).
notify: Callable[[str], None] = lambda text: print(f"[Рийлове] {text}")
progress: Callable[[str], None] = lambda text: print(f"[Рийлове] {text}")
state: Callable[[dict], None] = lambda info: None

_lock = threading.Lock()
current: "Job | None" = None
last_url = ""              # за „направи рийлове“ след „анализирай клипа“
last_folder: Path | None = None
last_found: list[dict] = []   # последното търсене на свободни клипове — за „направи рийлове от номер 2“
# Разговорът се помни и след рестарт (memory/conversation.json) — затова и последният клип, и списъкът.
LAST_FILE = config.BASE_DIR / "memory" / "reels_last.json"


def _save_last() -> None:
    try:
        LAST_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_FILE.write_text(json.dumps({"url": last_url, "found": last_found, "time": time.time()}, ensure_ascii=False),
                             encoding="utf-8")
    except OSError as e:
        print(f"[Рийлове] Не запазих последния клип: {e}")


def _load_last() -> None:
    global last_url, last_found
    try:
        data = json.loads(LAST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if time.time() - float(data.get("time") or 0) < 12 * 3600:  # колкото се помни и разговорът
        last_url, last_found = str(data.get("url") or ""), list(data.get("found") or [])


_load_last()

Word = tuple[str, float, float]   # (дума, начало, край) в секунди


class ReelError(RuntimeError):
    """Проблем, който се казва на сър с думи (частен клип, няма място…)."""


# =====================================================================================
#  Помощни
# =====================================================================================
def ffmpeg() -> str:
    import imageio_ffmpeg  # ffmpeg идва с пакета — не е нужно отделно инсталиране
    return imageio_ffmpeg.get_ffmpeg_exe()


def clock(seconds: float) -> str:
    """125 -> „2:05“, 3725 -> „1:02:05“."""
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def find_url(text: str) -> str | None:
    match = YOUTUBE_RE.search(text or "")
    if not match:
        return None
    url = match.group(0)
    return url if url.lower().startswith("http") else "https://" + url


def _run(cmd: list[str], timeout: float = 900, cwd: Path | None = None) -> bytes:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd, creationflags=_CREATE)
    except subprocess.TimeoutExpired as e:
        raise ReelError(f"видеото се обработваше повече от {max(1, round(timeout / 60))} мин. — YouTube го дава бавно "
                        f"в момента, опитайте пак по-късно") from e
    if result.returncode:
        error = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ReelError(f"ffmpeg: {error[-1][:200] if error else result.returncode}")
    return result.stdout


def _log(cmd: list[str], cwd: Path, timeout: float = 300) -> str:
    """Какво ffmpeg пише в журнала си (размер на кадъра, смени на сцената…)."""
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd,
                          timeout=timeout, creationflags=_CREATE).stderr


def _safe_name(text: str, limit: int = 60) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", text)
    return re.sub(r"\s+", " ", text).strip(" .")[:limit].strip(" .") or "клип"


def _explain(message: str) -> str:
    """Грешката на yt-dlp -> изречение за сър."""
    known = [("Private video", "клипът е частен"), ("confirm your age", "клипът е с възрастово ограничение"),
             ("members-only", "клипът е само за абонати на канала"), ("unavailable", "клипът не е достъпен"),
             ("Unsupported URL", "това не е адрес на клип от YouTube"), ("HTTP Error 429", "YouTube ограничи заявките — опитайте след малко"),
             ("getaddrinfo", "няма връзка с интернет")]
    for needle, text in known:
        if needle.lower() in message.lower():
            return text
    return message.replace("ERROR: ", "").splitlines()[0][:200]


def _ask_text(prompt: str, temperature: float = 0.3) -> str | None:
    """Отговорът на езиковия модел на Орион като текст (или None)."""
    from . import vision
    if vision.client is None:
        return None
    try:
        reply = vision.client.chat.completions.create(
            model=vision.model, temperature=temperature, messages=[{"role": "user", "content": prompt}],
            **({"reasoning_effort": "none"} if config.LLM_REASONING_EFFORT else {}))
        return re.sub(r"<think>.*?</think>", "", reply.choices[0].message.content or "", flags=re.DOTALL).strip()
    except Exception as e:  # noqa: BLE001 — без отговор рийлът пак става
        print(f"[Рийлове] Езиковият модел: {e}")
        return None


def _ask_model(prompt: str, temperature: float = 0.3) -> dict | None:
    """JSON отговор от езиковия модел на Орион (или None)."""
    text = _ask_text(prompt, temperature)
    try:
        return json.loads(text[text.find("{"):text.rfind("}") + 1]) if text else None
    except ValueError as e:
        print(f"[Рийлове] Езиковият модел: {e}")
        return None


_LANGUAGES = {"en": "английски", "bg": "български", "ru": "руски", "uk": "украински", "sr": "сръбски",
              "mk": "македонски", "de": "немски", "fr": "френски", "es": "испански", "it": "италиански",
              "pt": "португалски", "pl": "полски", "ro": "румънски", "el": "гръцки", "tr": "турски",
              "nl": "нидерландски", "ja": "японски", "ko": "корейски", "zh": "китайски", "ar": "арабски",
              "hi": "хинди"}


def _language(info: dict, moment: "Moment | None" = None) -> str:
    """На какъв език да са заглавието и хаштаговете: езикът на клипа — нищо не се превежда.
    Първо какво се говори в самия откъс, после езикът, който YouTube знае за клипа."""
    if config.REEL_TITLE_LANGUAGE:
        return f"{config.REEL_TITLE_LANGUAGE} език"
    for code in ((moment.language if moment else ""), info.get("language") or ""):
        name = _LANGUAGES.get(str(code).lower().split("-")[0])
        if name:
            return f"{name} език — езика на клипа, НЕ превеждай"
    return "езика, на който е клипът (като заглавието му) — НЕ превеждай"


def _title_and_tags(data: dict | None, fallback: str) -> tuple[str, list[str]]:
    data = data or {}
    title = str(data.get("title") or "")
    tags = [t if str(t).startswith("#") else f"#{t}" for t in data.get("hashtags") or [] if str(t).strip()]
    tags = list(dict.fromkeys([re.sub(r"\s+", "", str(t)) for t in tags + re.findall(r"#\w+", title)]))[:5]
    title = re.sub(r"\s*#\w+", "", title).strip(" „“\"'")[:70]  # хаштаговете не са част от заглавието
    if "#shorts" not in [t.lower() for t in tags]:
        tags.append("#shorts")
    return title or fallback[:60], tags


# =====================================================================================
#  Клипът и коментарите
# =====================================================================================
def fetch(url: str, comments: bool = True) -> dict:
    """Данните за клипа от YouTube: заглавие, продължителност, heatmap, глави, коментари, формати, субтитри."""
    import yt_dlp
    options = {
        "quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
        "js_runtimes": {"node": {}},  # YouTube изисква JavaScript за адресите на видеото
        "getcomments": comments,
        # 400 от най-харесваните коментари, без отговорите — стигат, за да се видят реакциите.
        "extractor_args": {"youtube": {"max_comments": ["400", "400", "0", "0"], "comment_sort": ["top"]}},
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise ReelError(_explain(str(e))) from e
    if info.get("is_live") or not info.get("duration"):
        raise ReelError("клипът е на живо — опитайте, след като приключи")
    return info


# =====================================================================================
#  0. Лиценз — рийлове само от клипове, които авторът е пуснал свободно
# =====================================================================================
# В YouTube авторът избира лиценза: стандартният — авторските права са запазени; „Creative Commons —
# Признание“ (CC BY 3.0) — всеки може да ползва клипа, и в свои видеа, ако посочи автора.
FREE_LICENSE_RE = re.compile(r"creative commons|public domain|\bcc0\b|\bcc[ -]by\b", re.IGNORECASE)
CC_BY = "CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/)"
_BRANDS = (r"national geographic|nat ?geo|pbs|bbc|discovery channel|netflix|hbo|disney|pixar|marvel|dreamworks|"
           r"history channel|cnn|fox news|fox sports|sky sports|espn|dazn|nfl|nba|nhl|ufc|wwe|uefa|fifa|"
           r"premier league|champions league|la ?liga|formula ?1|бнт|bnt|бтв|btv|нова тв")
# Много „свободни“ клипове всъщност са чужди: друг канал ги е качил и е избрал Creative Commons, без да
# има право. Признаци за това — (израз, къде се търси, защо е риск). Последната дума е на Content ID в
# YouTube, но с тях рискът от претенция за авторски права пада много.
RISKS = [
    (re.compile(r"copyright disclaimer|fair use|no copyright infringement|(?:not|no) (?:\w+ )?intend\w* to infringe|"
                r"rights? (?:of|belong\w*|go(?:es)?) (?:to )?(?:the )?(?:copyright )?(?:holder|owner)|"
                r"i do(?:n'?t| not) own|all (?:the )?credits? (?:go|goes|to)|section 107|не притежавам|"
                r"правата (?:са|принадлежат) на", re.IGNORECASE),
     "description", "в описанието пише, че правата са на някой друг"),
    (re.compile(rf"\b(?:{_BRANDS})\b", re.IGNORECASE), "title", "в заглавието е чужда марка — вероятно е качен от чужд канал"),
    (re.compile(r"official (?:music )?video|official audio|\blyrics?\b|full album|\(audio\)|remix|nightcore|slowed|"
                r"8d audio|текст(?:ове)? на песен", re.IGNORECASE),
     "title", "това е музика — тя почти винаги е със защитени права"),
    (re.compile(r"full movie|цял филм|целия филм|бг аудио|бг суб|episode \d|епизод \d|season \d|сезон \d|"
                r"фильм\w*|сериал\w*|кинофильм|\d+\s*(?:-\s*\d+\s*)?сери[яи]\b|\bсерия\s*\d", re.IGNORECASE),
     "title", "това е филм или сериал"),
    (re.compile(r"compilation|компилация|try not to laugh|опитайте се да не се смеете|tik ?tok|тик ?ток", re.IGNORECASE),
     "title", "това е компилация от чужди клипове"),
    (re.compile(r"highlights|обзор на мача|\bголове|\bgoals\b|\bvs\.? .+\d{1,2}[/.]\d{1,2}", re.IGNORECASE),
     "title-unverified", "кадри от мачове — правата са на лигите и телевизиите"),
]


def license_check(info: dict) -> tuple[bool, str]:
    """(може ли да се правят рийлове, защо). Може само ако авторът е избрал Creative Commons и няма
    признаци, че клипът е чужд."""
    if not FREE_LICENSE_RE.search(info.get("license") or ""):
        return False, "клипът е със стандартния лиценз на YouTube — авторските права са запазени"
    title, channel = info.get("title") or "", (info.get("channel") or info.get("uploader") or "").lower()
    for pattern, where, why in RISKS:
        if where == "title-unverified" and info.get("channel_is_verified"):
            continue  # официален канал (на отбора, на клуба) — неговите кадри
        text = f"{title}\n{info.get('description') or ''}" if where == "description" else title
        found = pattern.search(text)
        if found and found[0].lower() not in channel:  # официалният канал на марката може
            return False, f"{why} („{found[0].strip()}“)"
    return True, "Creative Commons — Признание (CC BY): позволено е ползване с посочване на автора"


def credit_line(info: dict) -> str:
    """Редът, който лицензът изисква в описанието на всеки рийл (на английски — разбира се навсякъде)."""
    url = f"https://youtu.be/{info['id']}" if info.get("id") else info.get("webpage_url", "")
    return (f"Source: \"{info.get('title')}\" by {info.get('channel') or info.get('uploader')} — {url} — "
            f"licensed under {CC_BY}")


_CC_SEARCH = "https://www.youtube.com/results?search_query={}&sp=EgIwAQ%253D%253D"  # филтърът „Creative Commons“


def find_free(topic: str, count: int = 5, remember: bool = True,
              exclude: set[str] | frozenset = frozenset()) -> tuple[list[dict], list[tuple[str, str]]]:
    """Клипове по тема, които авторите са пуснали свободно и нямат признаци, че са чужди. Търси с филтъра
    „Creative Commons“ на YouTube и проверява всеки клип поотделно. Връща (подходящите, [(пропуснат, защо)]).
    remember — за „направи рийлове от номер 2“; exclude — клипове, които да се пропуснат (по id)."""
    import concurrent.futures
    import urllib.parse

    import yt_dlp
    global last_found
    topic = topic.strip(" .,!?„“\"'")
    if not topic:
        raise ReelError("кажете за каква тема да търся")
    options = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": 4 * count + 4}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            entries = ydl.extract_info(_CC_SEARCH.format(urllib.parse.quote(topic)), download=False).get("entries") or []
    except yt_dlp.utils.DownloadError as e:
        raise ReelError(_explain(str(e))) from e
    # Готовите шортове (до минута, „#shorts“) не стават на нов рийл — те вече са такъв.
    entries = [e for e in entries if e.get("id") and e["id"] not in exclude and (e.get("duration") or 0) >= 60
               and "#short" not in (e.get("title") or "").lower()][:3 * count]

    def check(entry: dict) -> tuple[dict | None, str]:
        try:
            info = fetch(f"https://www.youtube.com/watch?v={entry['id']}", comments=False)
        except ReelError as e:
            return None, str(e)
        ok, why = license_check(info)
        return (info if ok else None), why

    found: list[dict] = []
    skipped: list[tuple[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(6) as pool:  # по един клип е ~2 с — заедно е бързо
        for entry, (info, why) in zip(entries, pool.map(check, entries)):
            if info and len(found) < count:
                found.append({"id": info["id"], "url": f"https://www.youtube.com/watch?v={info['id']}",
                              "title": info.get("title") or "", "channel": info.get("channel") or info.get("uploader") or "",
                              "duration": info.get("duration") or 0, "views": info.get("view_count") or 0,
                              "likes": info.get("like_count") or 0, "uploaded": info.get("upload_date") or "",
                              "heatmap": bool(info.get("heatmap")), "verified": bool(info.get("channel_is_verified"))})
            elif not info:
                skipped.append((entry.get("title") or entry["id"], why))
    if found and remember:
        last_found = found
        _save_last()
    return found, skipped


_ORDINALS = {"първ": 1, "втор": 2, "трет": 3, "четвърт": 4, "пет": 5, "шест": 6, "седм": 7, "осм": 8, "девет": 9,
             "десет": 10}


def pick_found(text: str) -> str | None:
    """„2“, „номер 2“, „второто“ -> линкът от последното търсене на свободни клипове (или None)."""
    text = (text or "").strip().lower()
    match = re.fullmatch(r"(?:номер|№|#)?\s*(\d{1,2})", text)
    number = int(match[1]) if match else next(
        (n for stem, n in _ORDINALS.items() if re.fullmatch(rf"(?:номер\s+)?{stem}\w*", text)), None)
    if number and 1 <= number <= len(last_found):
        return last_found[number - 1]["url"]
    return None


def _timestamp(match: re.Match) -> int:
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


def _baseline(values, width: int):
    """Средното на околните `width` секунди. В краищата клипът се „огледално“ продължава —
    иначе първите и последните секунди изглеждат като изкуствени върхове."""
    import numpy as np
    width = max(1, min(int(width), len(values) - 1)) | 1  # нечетно, за да е центрирано
    half = width // 2
    padded = np.pad(values, half, mode="reflect") if half else values
    return np.convolve(padded, np.ones(width) / width, mode="valid")


def _end_ramp(heat, duration: int) -> int | None:
    """Откъде гледанията растат без прекъсване до последната секунда (или None). Такава „рампа“
    са надписите накрая, клип в цикъл или превъртане до края — не интерес към момент."""
    import numpy as np
    level = _baseline(heat, max(5, duration // 40))
    if level.argmax() < duration - max(15, duration * 0.1):
        return None  # върхът не е в края
    top = level[-max(5, duration // 50):].max()
    low = np.nonzero(level < 0.3 * top)[0]  # последното място, където е било далеч под края
    if not len(low):
        return None
    start = int(low[-1]) + 1
    rising = float(np.mean(np.diff(level[start:]) >= -0.002)) if duration - start > 2 else 0.0
    return start if duration - start >= max(15, duration * 0.05) and rising > 0.7 else None


def _smooth(values, width: int):
    import numpy as np
    width = max(1, int(width))
    kernel = np.hanning(width + 2)[1:-1]
    return np.convolve(values, kernel / kernel.sum(), mode="same")


# =====================================================================================
#  1. Сигнали — къде зрителите реагират най-много
# =====================================================================================
@dataclass
class Moment:
    start: float
    end: float
    peak: int
    score: float                                  # сила на сигналите (гледания, коментари, звук)
    reasons: list[str] = field(default_factory=list)
    chapter: str = ""
    words: list[Word] = field(default_factory=list)   # какво се казва — време от началото на клипа
    language: str = ""
    transcribed: bool = False
    source: str = ""                               # „manual“/„auto“ (субтитри на YouTube) или „whisper“
    rating: float = 0.0                           # оценка на редактора 1–10 (0 — без реч)
    hook: str = ""
    why: str = ""
    title: str = ""
    hashtags: list[str] = field(default_factory=list)


def audio_energy(info: dict):
    """Силата на звука за всяка секунда (относително — над средното за клипа). Тегли само звука
    в най-ниско качество. None — ако клипът е твърде дълъг или няма звук."""
    import numpy as np
    duration = int(info["duration"])
    if duration > AUDIO_MAX_SECONDS:
        return None
    audios = [f for f in info.get("formats") or [] if str(f.get("protocol", "")).startswith("http")
              and f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")]
    if not audios:
        return None
    fmt = min(audios, key=lambda f: f.get("abr") or f.get("tbr") or 999)
    # Целият звук се тегли с yt-dlp (на части): ffmpeg направо от адреса получава дългите клипове с
    # ~2× скоростта на гледане — 90 минути звук биха се теглили 45 минути, на части — секунди.
    import tempfile

    import yt_dlp
    config.REELS_DIR.mkdir(parents=True, exist_ok=True)
    options = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
               "js_runtimes": {"node": {}}, "format": str(fmt["format_id"])}
    try:
        with tempfile.TemporaryDirectory(dir=config.REELS_DIR) as folder:
            options["outtmpl"] = str(Path(folder) / "audio.%(ext)s")
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([info.get("webpage_url") or info.get("original_url")])
            source = next(Path(folder).glob("audio.*"))
            pcm = _run([ffmpeg(), "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "8000",
                        "-f", "s16le", "-"], timeout=max(180, duration / 20))
    except (yt_dlp.utils.DownloadError, ReelError, StopIteration, OSError) as e:
        print(f"[Рийлове] Силата на звука: {e}")
        return None  # без нея анализът продължава с другите сигнали
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    seconds = min(duration, len(samples) // 8000)
    if not seconds:
        return None
    rms = np.sqrt(np.mean(samples[:seconds * 8000].reshape(seconds, 8000) ** 2, axis=1)) + 1.0
    db = 20 * np.log10(rms)
    energy = np.clip(db - np.median(db), 0, None)
    return np.pad(energy, (0, duration - seconds))


def analyze(info: dict, count: int, length: int, audio: Callable | None = audio_energy) -> tuple[list[Moment], list[str]]:
    """Най-силните `count` момента с дължина `length` секунди. Връща (моменти, по какво са намерени)."""
    import numpy as np
    duration = int(info["duration"])
    length = int(max(10, min(length, duration)))
    notes: list[str] = []

    heat = np.zeros(duration)
    for seg in info.get("heatmap") or []:
        a = int(seg["start_time"])
        b = min(duration, max(a + 1, int(math.ceil(seg["end_time"]))))
        heat[a:b] = np.maximum(heat[a:b], seg["value"])
    raw = heat.copy()  # за обясненията („гледат го отново — 80% от върха“)
    if heat.any():
        # Началото винаги е „най-гледано“ (всички започват оттам), а понякога и краят (надписи, клип
        # в цикъл, превъртане). Там гледанията се изравняват до нивото до тях — без изкуствен връх.
        intro = min(int(max(10, duration * 0.03)), duration - 1)
        heat[:intro] = np.minimum(heat[:intro], heat[intro])
        ramp = _end_ramp(heat, duration)
        outro = ramp if ramp is not None else duration - int(max(15, duration * 0.05))
        if 0 < outro < duration:
            heat[outro:] = np.minimum(heat[outro:], heat[outro - 1])
        # Истинският хайлайт изпъква спрямо съседните минути, не само спрямо целия клип.
        local = np.clip(heat - _baseline(heat, max(31, int(duration * 0.15))), 0, None)
        heat = 0.4 * heat / heat.max() + (0.6 * local / local.max() if local.any() else 0)
        notes.append("най-гледаните моменти в YouTube")

    mentions = np.zeros(duration)
    quotes: dict[int, list[tuple[int, str]]] = {}
    counted = 0
    for comment in info.get("comments") or []:
        text = comment.get("text") or ""
        stamps = {s for s in (_timestamp(m) for m in TIMESTAMP_RE.finditer(text)) if 0 <= s < duration}
        if not stamps or len(stamps) > 3:  # списък с глави („0:00 Интро, 1:20 …“) не е реакция
            continue
        likes = comment.get("like_count") or 0
        counted += 1
        for second in stamps:
            mentions[second] += 1 + math.log1p(likes)
            quotes.setdefault(second, []).append((likes, text))
    if mentions.any():
        mentions = _smooth(mentions, 9)
        notes.append(f"{counted} коментара с час" if counted > 1 else "един коментар с час")

    # Без данни за гледанията коментарите с час са малко (често един-два върха) — силата на звука
    # намира останалите моменти. Коментарите тежат повече: те са реакции на хора.
    energy = None
    if not heat.any() and audio:
        progress("Няма данни за гледанията — слушам и къде е най-силният звук." if mentions.any()
                 else "Няма данни за гледанията и коментари с час — слушам къде е най-силният звук.")
        energy = audio(info)
        if energy is not None and energy.any():
            notes.append("силата на звука (смях, викове, музика)")
    energy_weight = 0.2 if mentions.any() else 0.5

    parts = [(signal / signal.max(), weight) for signal, weight in ((heat, 0.65), (mentions, 0.35), (energy, energy_weight))
             if signal is not None and signal.any()]
    if duration <= length + 5:  # кратък клип — целият е един рийл
        return [Moment(0, duration, duration // 2, 1.0, ["клипът е кратък — целият става рийл"])], notes or ["целият клип"]
    if not parts:
        raise ReelError("не намерих откъде да позная най-интересните моменти (няма данни за гледанията, "
                        "коментари с час и звук)")
    score = sum(signal * weight for signal, weight in parts) / sum(weight for _, weight in parts)
    smooth = _smooth(score, max(3, length // 3))

    moments: list[Moment] = []
    work, best = smooth.copy(), float(smooth.max())
    chapters = info.get("chapters") or []
    for _ in range(max(1, count)):
        peak = int(work.argmax())
        if work[peak] <= 0 or work[peak] < 0.25 * best:
            break
        start = float(min(max(0, peak - 0.35 * length), duration - length))
        end = start + length
        reasons = []
        skip = int(max(10, duration * 0.03))  # без въведението — там „гледат“ всички
        if raw[skip:].any() and max(int(start), skip) < int(end):
            share = int(round(100 * raw[max(int(start), skip):int(end)].max() / raw[skip:].max()))
            reasons.append(f"зрителите го гледат отново ({min(share, 100)}% от най-гледания момент)")
        said = sorted((q for s in range(int(start), int(end)) for q in quotes.get(s, [])), reverse=True)
        if said:
            quote = re.sub(r"\s+", " ", TIMESTAMP_RE.sub("", said[0][1])).strip(" -–:,")[:90]
            reasons.append((f"{len(said)} коментара го споменават" if len(said) > 1 else "коментар го споменава")
                           + (f", напр. „{quote}“" if quote else ""))
        if energy is not None and energy.any() and energy[int(start):int(end)].max() >= 0.5 * energy.max():
            reasons.append("най-силен звук (смях, викове, музика)")
        chapter = next((c.get("title", "") for c in chapters if c.get("start_time", 0) <= peak < c.get("end_time", 0)), "")
        moments.append(Moment(start, end, peak, float(smooth[peak]), reasons, chapter))
        # Следващият връх не бива да дава рийл, който се застъпва с този (+2 с разстояние).
        low, high = int(max(0, start - 0.65 * length - 2)), int(min(duration, end + 0.35 * length + 2))
        work[low:high] = -1
    return moments, notes


def describe(info: dict, moments: list[Moment], notes: list[str]) -> str:
    """Анализът с думи — за сър."""
    views = info.get("view_count")
    views_text = f", {views:,} гледания".replace(",", " ").replace(" ", ",", 1) if views else ""
    head = (f"„{info.get('title')}“ ({clock(info['duration'])}{views_text}, "
            f"{len(info.get('comments') or [])} прочетени коментара). ")
    listed = "; ".join(f"{i}) {clock(m.start)}–{clock(m.end)}" + (f" „{m.chapter}“" if m.chapter else "")
                       + (" — " + ", ".join(m.reasons) if m.reasons else "")
                       + (f" (редакторът: {m.rating:.0f}/10 — {m.why})" if m.rating else "")
                       for i, m in enumerate(moments, 1))
    return f"{head}Най-силните моменти според {', '.join(notes)}: {listed}."


def analyze_url(url: str, count: int = 5, seconds: int = config.REEL_SECONDS) -> str:
    global last_url
    info = fetch(url)
    moments, notes = analyze(info, count, seconds)
    last_url = url
    _save_last()
    free, why = license_check(info)
    if free or not config.REEL_FREE_ONLY:
        return describe(info, moments, notes) + f" Лиценз: {why}. Кажете „направи рийлове от този клип“, за да ги изрежа."
    return describe(info, moments, notes) + f" Рийлове от него не правя: {why}."


# =====================================================================================
#  2. Какво се казва — субтитрите на YouTube (бързо) или Whisper (ако ги няма)
# =====================================================================================
def _json3_words(data: dict) -> list[Word]:
    """Думите от субтитрите на YouTube (формат json3) с началото на всяка дума."""
    words: list[list] = []
    for event in data.get("events") or []:
        segs = [s for s in event.get("segs") or [] if (s.get("utf8") or "").strip()]
        if not segs:
            continue
        start, span = event.get("tStartMs", 0) / 1000, event.get("dDurationMs", 0) / 1000
        if any("tOffsetMs" in s for s in segs):  # автоматичните: време за всяка дума
            for seg in segs:
                for token in seg["utf8"].split():
                    words.append([token, start + seg.get("tOffsetMs", 0) / 1000, 0.0])
        else:  # ръчните: цял ред — думите се разпределят равномерно в него
            tokens = " ".join(s["utf8"] for s in segs).split()
            step = span / max(1, len(tokens)) if span else 0.3
            words += [[token, start + i * step, 0.0] for i, token in enumerate(tokens)]
    words = [w for w in words if not re.fullmatch(r"\[.*\]|\(.*\)|♪+", w[0])]  # [Музика], [Смях]
    words.sort(key=lambda w: w[1])
    for i, word in enumerate(words):
        following = words[i + 1][1] if i + 1 < len(words) else word[1] + 0.6
        word[2] = max(word[1] + 0.05, min(following, word[1] + 0.9))
    return [tuple(w) for w in words]


# Автоматичните субтитри на YouTube са добри само за английски (на български са неразбираеми).
AUTO_CAPTION_LANGUAGES = {"en"}


def youtube_words(info: dict) -> tuple[list[Word], str, str] | None:
    """Субтитрите на клипа от YouTube: ръчните на езика му или автоматичните — оригиналните, не
    преведените. None, ако няма (нов клип или език без автоматични субтитри, напр. български)."""
    import urllib.request
    language = (info.get("language") or "").lower()
    manual, auto = info.get("subtitles") or {}, info.get("automatic_captions") or {}
    choices = []
    if language:
        choices += [(formats, key, "manual") for key, formats in manual.items()
                    if key.lower().split("-")[0] == language.split("-")[0]]
    choices += [(formats, key[:-5], "auto") for key, formats in auto.items()
                if key.endswith("-orig") and key[:-5].split("-")[0] in AUTO_CAPTION_LANGUAGES]
    for formats, lang, kind in choices:
        fmt = next((f for f in formats or [] if f.get("ext") == "json3"), None)
        if not fmt:
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(fmt["url"], headers=_UA), timeout=20) as response:
                words = _json3_words(json.load(response))
        except (OSError, ValueError):
            continue
        if len(words) > 20:
            return words, lang, kind
    return None


def _audio(info: dict, start: float, end: float):
    """Звукът на откъс (16 kHz, моно) — само звуковата пътечка, бързо."""
    import numpy as np

    def read():
        video, audio = _formats(info)
        fmt = audio or video
        return _run([ffmpeg(), "-v", "error", "-headers", _headers(fmt), "-ss", f"{start:.2f}", "-to", f"{end:.2f}",
                     "-i", fmt["url"], "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], timeout=600)
    return np.frombuffer(_fresh(info, read), dtype=np.int16).astype(np.float32) / 32768.0


def _whisper_words(info: dict, start: float, end: float) -> tuple[list[Word], str]:
    """Whisper за откъс, когато YouTube няма субтитри. Време — от началото на клипа."""
    from . import speech
    speech.load()  # на видеокартата, ако има място — иначе speech.transcribe ползва процесора
    audio = _audio(info, start, end)
    if not len(audio):
        return [], ""
    language, words = speech.transcribe(audio)
    return [(w, s + start, e + start) for w, s, e in words], language


def _real_speech(words: list[Word]) -> bool:
    """Истинска реч ли е: поне 12 думи и не една и съща фраза отново и отново — така Whisper
    „чува“ музика и шум („I don't know what to do, but I don't know what to do…“)."""
    return len(words) >= 12 and not _looped(words)


def _looped(words: list[Word]) -> bool:
    """Една и съща фраза отново и отново (под една трета различни думи)."""
    tokens = [t for t in (re.sub(r"\W+", "", w.lower()) for w, _, _ in words) if t]
    return len(tokens) >= 8 and len(set(tokens)) / len(tokens) < 0.35


def _lines(words: list[Word]) -> list[tuple[float, float, str]]:
    """Думите на изречения/редове — за редактора (край на изречение, пауза или 14 думи)."""
    lines, current = [], []
    for i, word in enumerate(words):
        current.append(word)
        gap = words[i + 1][1] - word[2] if i + 1 < len(words) else 9.0
        if re.search(r"[.!?…]$", word[0]) or gap > 0.7 or len(current) >= 14:
            lines.append((current[0][1], current[-1][2], " ".join(w for w, _, _ in current)))
            current = []
    return lines


# =====================================================================================
#  3. Редактор — самостоятелен откъс с кука, изрязан по изречения, с оценка
# =====================================================================================
EDITOR_PROMPT = """Ти си опитен редактор на YouTube Shorts. Това е откъс от клипа „{title}“ — редове с време
в секунди от началото на клипа:
{lines}

Зрителите харесват това място: {reasons}.
Избери най-добрия САМОСТОЯТЕЛЕН рийл между {low} и {high} секунди (по възможност около {target}):
- започва с кука — изречение, което веднага грабва вниманието (не с „и“, „така“, поздрав или по средата на мисъл);
- завършва с поанта, реакция или край на мисъл — не по средата на изречение;
- разбира се без останалата част от клипа.
Дай оценка 1–10 колко добър рийл става (10 — ще го гледат докрай и ще го споделят), кратко закачливо
заглавие (до 60 знака, без хаштагове) и 4 хаштага — на {language} (имената остават както са).
Ако текстът е без точки и главни букви, сам прецени къде започва и къде свършва изречението.
Отговори САМО с JSON: {{"start": секунда, "end": секунда, "score": 1-10, "hook": "първото изречение",
"first_words": "първите 4 думи на рийла, дословно от текста", "last_words": "последните 4 думи, дословно от текста",
"why": "защо е добър, до 12 думи, на български", "title": "...", "hashtags": ["#...", "#..."]}}"""


_SENTENCE_END = re.compile(r"[.!?…][\"“»)]*$")


def _padded(words: list[Word], begin: float, finish: float, duration: float) -> tuple[float, float]:
    """Малко въздух преди първата и след последната дума — но без да се хване съседна дума
    („…persuasions. The“)."""
    before = max((e for _, s, e in words if e <= begin + 0.01), default=0.0)
    after = min((s for _, s, e in words if s >= finish - 0.01), default=duration)
    return max(0.0, begin - 0.15, before + 0.02), min(duration, finish + 0.5, max(finish, after - 0.05))


def _punctuated(lines: list[tuple[float, float, str]]) -> bool:
    """Има ли текстът препинателни знаци (автоматичните субтитри на YouTube нямат)."""
    return sum(bool(_SENTENCE_END.search(text)) for _, _, text in lines) >= max(2, len(lines) // 6)


def _norm(word: str) -> str:
    return re.sub(r"[^\w']", "", word.lower())


def _find_phrase(words: list[Word], phrase: str, near: float, last: bool = False, window: float = 15.0) -> int | None:
    """Къде в думите е фразата, която редакторът е цитирал дословно (близо до `near` секунди): индексът на
    първата ѝ дума — или на последната, ако last. None — ако не е намерена."""
    tokens = [t for t in (_norm(w) for w in str(phrase or "").split()) if t]
    tokens = tokens[-4:] if last else tokens[:4]
    if len(tokens) < 2:
        return None
    found = [i for i in range(len(words) - len(tokens) + 1)
             if abs(words[i][1] - near) <= window and [_norm(w) for w, _, _ in words[i:i + len(tokens)]] == tokens]
    if not found:
        return None
    best = min(found, key=lambda i: abs(words[i][1] - near))
    return best + len(tokens) - 1 if last else best


PUNCTUATE_PROMPT = """Това са автоматични субтитри — без точки и главни букви. Сложи точки, въпросителни,
удивителни, запетаи и главни букви, за да личи къде започва и свършва всяко изречение. НЕ сменяй, не добавяй и
не махай думи. Отговори САМО с текста.

{text}"""


def _whole_sentences(moment: Moment, low: float, high: float, duration: float) -> None:
    """Автоматични субтитри: моделът слага препинателните знаци в текста около избрания рийл (без да
    сменя думите), а рийлът се премества до началото и края на изречение. Само за избраните рийлове."""
    import difflib
    words = [w for w in moment.words if moment.start - 12 <= w[1] <= moment.end + 10]
    text = _ask_text(PUNCTUATE_PROMPT.format(text=" ".join(w for w, _, _ in words)), 0.1) if len(words) > 8 else None
    if not text:
        return
    marked = text.split()
    match = difflib.SequenceMatcher(a=[_norm(w) for w, _, _ in words], b=[_norm(t) for t in marked], autojunk=False)
    starts, ends = set(), set()  # индекси в words: дума, с която започва / свършва изречение
    for block in match.get_matching_blocks():
        for k in range(block.size):
            i, j = block.a + k, block.b + k
            # Първата дума на парчето не е задължително начало на изречение — то започва 12 с по-рано.
            if j > 0 and _SENTENCE_END.search(marked[j - 1]):
                starts.add(i)
            if _SENTENCE_END.search(marked[j]):
                ends.add(i)
    if not starts or not ends:
        return
    first = min(range(len(words)), key=lambda i: abs(words[i][1] - (moment.start + 0.15)))
    last = min(range(len(words)), key=lambda i: abs(words[i][2] - (moment.end - 0.5)))
    # Началото: най-близкото начало на изречение — за предпочитане преди избраното; краят — най-близкият край.
    begins = sorted(starts, key=lambda i: (i > first + 3, abs(i - first)))[:4]
    finishes = sorted(ends, key=lambda i: abs(i - last))[:4]
    # Първо и началото, и краят на изречение; ако дължината не позволява — поне едното от двете.
    pairs = ([(a, b) for a in begins for b in finishes] + [(a, last) for a in begins] + [(first, b) for b in finishes])
    for a, b in pairs:
        if b > a and low - 1 <= words[b][2] - words[a][1] <= high + 1:
            moment.start, moment.end = _padded(moment.words, words[a][1], words[b][2], duration)
            sentence_end = next((i for i in sorted(ends) if i >= a), b)
            moment.hook = " ".join(w for w, _, _ in words[a:min(sentence_end + 1, a + 25)])
            return


def _sentence_bounds(lines: list[tuple[float, float, str]], first: int, last: int,
                     low: float, high: float) -> tuple[int, int]:
    """Рийлът започва в началото на изречение и свършва в края му — редовете се делят и при пауза или
    след 14 думи, затова избраният ред може да е продължение на изречение („streets in a real city.“).
    Без препинателни знаци (автоматични субтитри) няма по какво да се съди — остава както е."""
    ends = [bool(_SENTENCE_END.search(text)) for _, _, text in lines]
    if not _punctuated(lines):
        return first, last

    def span(a: int, b: int) -> float:
        return lines[b][1] - lines[a][0]

    def starts(k: int) -> bool:  # първият ред е изрязан от целия клип — начало е само ако е с главна буква
        return ends[k - 1] if k else lines[0][2][:1].isupper()

    if not starts(first):
        back = next((k for k in range(first - 1, max(-1, first - 5), -1) if starts(k)), None)
        ahead = next((k for k in range(first + 1, min(last + 1, first + 5)) if starts(k)), None)
        if back is not None and span(back, last) <= high:
            first = back
        elif ahead is not None and span(ahead, last) >= low:
            first = ahead
    if not ends[last]:
        ahead = next((k for k in range(last + 1, min(len(lines), last + 6)) if ends[k]), None)
        back = next((k for k in range(last - 1, first - 1, -1) if ends[k]), None)
        if ahead is not None and span(first, ahead) <= high:
            last = ahead
        elif back is not None and span(first, back) >= low:
            last = back
    return first, last


def edit(info: dict, moment: Moment, low: float, high: float, target: float) -> bool:
    """Редакторът избира откъса вътре в кандидата. True — ако е избрал (иначе остава както е)."""
    lines = _lines(moment.words)
    if len(lines) < 2:
        return False
    listing = "\n".join(f"[{s:.1f}–{e:.1f}] {t}" for s, e, t in lines)
    data = _ask_model(EDITOR_PROMPT.format(
        title=info.get("title"), lines=listing[:6000], reasons=", ".join(moment.reasons) or "силен момент",
        low=int(low), high=int(high), target=int(target), language=_language(info, moment)))
    try:
        start, end = float(data["start"]), float(data["end"])
    except (TypeError, KeyError, ValueError):
        return False
    # Отрязва се по цели редове: най-близкият ред до избраното начало и до избрания край.
    first = min(range(len(lines)), key=lambda k: abs(lines[k][0] - start))
    last = min(range(first, len(lines)), key=lambda k: abs(lines[k][1] - end))
    while last > first and lines[last][1] - lines[first][0] > high:
        last -= 1
    while lines[last][1] - lines[first][0] < low and last + 1 < len(lines):
        last += 1
    while lines[last][1] - lines[first][0] < low and first > 0:
        first -= 1
    first, last = _sentence_bounds(lines, first, last, low, high)
    begin, finish, hook = lines[first][0], lines[last][1], lines[first][2]
    if not _punctuated(lines):
        # Автоматични субтитри — без точки не личи къде е изречението. Реже се по думите, които редакторът
        # е посочил дословно (той вижда смисъла), а не по цели редове.
        words = moment.words
        # Куката (първото изречение) е по-точна от „first_words“ — там моделът понякога слага и края на
        # предишното изречение („away and by the“) или само една дума.
        hook_words = str(data.get("hook") or "").split()
        i = next((found for phrase in (hook_words[:4], hook_words[1:5], hook_words[:3])
                  if (found := _find_phrase(words, " ".join(phrase), begin)) is not None),
                 _find_phrase(words, data.get("first_words"), begin))
        j = _find_phrase(words, data.get("last_words"), finish, last=True)
        new_begin = words[i][1] if i is not None else begin
        new_finish = words[j][2] if j is not None and (i is None or j > i) else finish
        if low - 1 <= new_finish - new_begin <= high + 1:
            begin, finish = new_begin, new_finish
            if i is not None:
                hook = " ".join(w for w, _, _ in words[i:i + 15])
    if finish - begin < low - 1:
        return False  # речта е твърде малко за рийл — остава откъсът по сигналите
    moment.start, moment.end = _padded(moment.words, begin, finish, float(info["duration"]))
    moment.end = min(moment.end, moment.start + high + 1)
    try:
        moment.rating = max(1.0, min(10.0, float(data.get("score") or 5)))
    except (TypeError, ValueError):
        moment.rating = 5.0
    moment.hook = hook[:200]  # дословно от субтитрите — моделът понякога превежда
    moment.why = str(data.get("why") or "")[:160]
    moment.title, moment.hashtags = _title_and_tags(data, moment.chapter or info.get("title") or "")
    return True


def select(info: dict, count: int, seconds: int) -> tuple[list[Moment], list[str]]:
    """Кандидати по сигналите -> какво се казва в тях -> редакторът избира и оценява -> най-добрите."""
    duration = float(info["duration"])
    low, high = max(12, round(seconds * 0.6)), min(180, round(seconds * 1.35))
    candidates, notes = analyze(info, min(10, count + EXTRA_CANDIDATES), seconds)
    captions = youtube_words(info)
    if captions:
        notes.append("субтитрите на клипа")
    for index, moment in enumerate(candidates, 1):
        _state(f"слушам момент {index}/{len(candidates)}")
        a, b = max(0.0, moment.start - 0.35 * seconds), min(duration, moment.end + 0.35 * seconds)
        if captions:  # субтитрите са готови — малко повече текст, за да личи къде са изреченията
            a, b = max(0.0, a - 10), min(duration, b + 10)
            moment.words = [w for w in captions[0] if a <= w[1] < b]
            moment.language, moment.source = captions[1], captions[2]
        else:
            progress(f"Слушам какво се казва в момент {index} от {len(candidates)} ({clock(moment.start)})…")
            moment.words, moment.language = _whisper_words(info, a, b)
            moment.source = "whisper"
        moment.transcribed = True
        if not _real_speech(moment.words):  # музика, шум — Whisper „чува“ повтаряща се фраза
            moment.words = []
        if moment.words:  # има реч — редакторът избира откъса
            _state(f"редакторът гледа момент {index}/{len(candidates)}")
            edit(info, moment, low, high, seconds)
    if any(m.rating for m in candidates):
        notes.append("оценката на редактора (кука, поанта, смисъл)")
    top = max(m.score for m in candidates) or 1.0
    ranked = sorted(candidates, key=lambda m: 0.5 * m.score / top + 0.5 * (m.rating / 10 if m.rating else 0.5),
                    reverse=True)
    chosen: list[Moment] = []
    for moment in ranked:
        if all(moment.end <= c.start or moment.start >= c.end for c in chosen):
            chosen.append(moment)
        if len(chosen) == count:
            break
    for moment in chosen:
        if moment.words and moment.rating and not _punctuated(_lines(moment.words)):
            _whole_sentences(moment, low, high, duration)
    return chosen, notes


# =====================================================================================
#  4. Рийлът: теглене на откъса -> кадриране -> субтитри -> вертикално видео -> корица
# =====================================================================================
def _headers(fmt: dict) -> str:
    return "".join(f"{k}: {v}\r\n" for k, v in (fmt.get("http_headers") or {}).items())


def _formats(info: dict) -> tuple[dict, dict | None]:
    """Най-доброто видео до 1080p (и отделно звукът), което ffmpeg може да чете направо."""
    formats = [f for f in info.get("formats") or [] if str(f.get("protocol", "")).startswith("http") and f.get("url")]
    small = lambda f: min(f.get("width") or 9999, f.get("height") or 9999) <= 1080  # noqa: E731 — и вертикалните
    videos = [f for f in formats if f.get("vcodec") not in (None, "none") and f.get("acodec") in (None, "none") and small(f)]
    audios = [f for f in formats if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")]
    # Оригиналът е по-добър от вариантите на YouTube: „-sr“ (изкуствено увеличена картина) и
    # „drc“ (сгъстен звук).
    original = lambda f: "-sr" not in str(f.get("format_id")) and "drc" not in str(f.get("format_id"))  # noqa: E731
    if videos and audios:
        video = max(videos, key=lambda f: (min(f.get("width") or 0, f.get("height") or 0), original(f),
                                           str(f.get("vcodec", "")).startswith("avc"), f.get("tbr") or 0))
        return video, max(audios, key=lambda f: (original(f), f.get("abr") or f.get("tbr") or 0))
    muxed = [f for f in formats if f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none")]
    if muxed:
        return max(muxed, key=lambda f: f.get("height") or 0), None
    raise ReelError("не намерих видео, което мога да изрежа")


def _fresh(info: dict, action: Callable):
    """YouTube понякога отказва адрес за момент (403) — тогава взима нови адреси и опитва пак."""
    try:
        return action()
    except ReelError as e:
        if "403" not in str(e):
            raise
        progress("YouTube отказа достъп за момент — взимам нови адреси и опитвам пак.")
        info["formats"] = fetch(info.get("webpage_url") or info.get("original_url"), comments=False)["formats"]
        return action()


def _grab(info: dict, start: float, end: float, dest: Path) -> None:
    """Откъсът без прекодиране. Копирането започва от ключовия кадър преди `start` (картината) и от
    по-ранно място в звука — различно за всеки клип, затова часовете остават тези от YouTube
    (-copyts): така картината и звукът са точно един спрямо друг, а рийлът се реже по час (_start)."""
    def grab():
        video, audio = _formats(info)
        cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-copyts"]
        for fmt in (video, audio) if audio else (video,):
            cmd += ["-headers", _headers(fmt), "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", fmt["url"]]
        cmd += ["-map", "0:v:0", "-map", "1:a:0" if audio else "0:a:0?", "-c", "copy", str(dest)]
        _run(cmd, timeout=900)
    _fresh(info, grab)


def _start(folder: Path, segment: Path) -> float:
    """Часът в клипа, от който започва изтегленият откъс (-ss при рязането се брои от него)."""
    found = re.search(r"start: (-?[\d.]+)", _log([ffmpeg(), "-hide_banner", "-i", segment.name], folder))
    if not found:
        raise ReelError("не разбрах откъде започва изтегленият откъс")
    return float(found[1])


def _transcript(segment: Path, offset: float, length: float) -> tuple[str, list[Word]]:
    """Думите в рийла с време спрямо началото му — когато кандидатът не е бил преслушан."""
    import numpy as np

    from . import speech
    speech.load()
    pcm = _run([ffmpeg(), "-v", "error", "-ss", f"{offset:.2f}", "-t", f"{length:.2f}", "-i", str(segment),
                "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], timeout=300)
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return speech.transcribe(audio) if len(audio) else ("", [])


def _video_size(folder: Path, segment: Path) -> tuple[int, int] | None:
    size = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", _log([ffmpeg(), "-hide_banner", "-i", segment.name], folder))
    return (int(size[1]), int(size[2])) if size else None


def _black_bars(folder: Path, segment: Path, at: float) -> str:
    """„crop=…,“ ако кадърът има черни ленти (стари клипове, 4:3 в 16:9) — иначе празно."""
    log = _log([ffmpeg(), "-hide_banner", "-ss", f"{at:.2f}", "-t", "3", "-i", segment.name,
                "-vf", "cropdetect=limit=24:round=2:reset=0", "-f", "null", "-"], folder, timeout=120)
    size = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", log)
    crops = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", log)
    if not size or not crops:
        return ""
    full_w, full_h = map(int, size.groups())
    w, h, x, y = map(int, crops[-1])
    removes = (w < full_w * 0.96 or h < full_h * 0.96)
    plausible = w * h > full_w * full_h * 0.5  # тъмна сцена не е „черни ленти“
    return f"crop={w}:{h}:{x}:{y}," if removes and plausible else ""


def _scene_cuts(folder: Path, segment: Path, offset: float, length: float, bars: str) -> list[float]:
    """Кога се сменя сцената (кадърът) — секунди от началото на рийла."""
    log = _log([ffmpeg(), "-hide_banner", "-ss", f"{offset:.2f}", "-t", f"{length:.2f}", "-i", segment.name,
                "-vf", f"{bars}scale=320:-2,select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"], folder)
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", log)]


def _x_expression(keys: list[tuple[float, float, bool]]) -> str:
    """Изразът на ffmpeg за мястото на рамката: при смяна на сцената — скок (като монтаж), вътре
    в сцената — плавно движение между ключовите точки (като камераман)."""
    expression = f"{keys[-1][1]:.0f}"
    for k in range(len(keys) - 2, -1, -1):
        (t0, x0, _), (t1, x1, new_scene) = keys[k], keys[k + 1]
        piece = (f"{x0:.0f}" if new_scene or abs(x1 - x0) < 2
                 else f"{x0:.1f}+({x1 - x0:.1f})*(t-{t0:.2f})/{max(t1 - t0, 0.01):.2f}")
        expression = f"if(lt(t,{t1:.2f}),{piece},{expression})"
    return expression


TOP_HEIGHT = 672   # „стрийм“: камерата горе (1080×672), играта отдолу (1080×1248)


def _stream_layout(width: int, height: int, cx: float, cy: float, face_w: float) -> str:
    """Геймърски клип с камера в ъгъла: камерата — горе, увеличена; играта — отдолу (средата)."""
    even = lambda v: int(v) // 2 * 2  # noqa: E731
    box_w = min(width * 0.45, max(face_w * width * 3.0, width * 0.15))  # уебкамерата е ~3 лица широка
    box_h = box_w * TOP_HEIGHT / WIDTH
    if box_h > height * 0.6:
        box_h = height * 0.6
        box_w = box_h * WIDTH / TOP_HEIGHT
    box_x = min(max(cx * width - box_w / 2, 0), width - box_w)
    box_y = min(max(cy * height - box_h * 0.45, 0), height - box_h)  # лицето — малко над средата
    game_w = min(width, height * WIDTH / (HEIGHT - TOP_HEIGHT))
    return (f"split=2[cam][game];"
            f"[cam]crop={even(box_w)}:{even(box_h)}:{even(box_x)}:{even(box_y)},scale={WIDTH}:{TOP_HEIGHT}[top];"
            f"[game]crop={even(game_w)}:{height}:{even((width - game_w) / 2)}:0,"
            f"scale={WIDTH}:{HEIGHT - TOP_HEIGHT}[bottom];[top][bottom]vstack,setsar=1")


def _corner_camera(per_frame: list[list[tuple[float, float, float]]]) -> tuple[float, float, float] | None:
    """Камерата на стриймър: лице, което стои на едно място в ъгъла в поне половината кадри
    (героите в играта се движат — те не са камера). (x, y, ширина) или None."""
    import numpy as np
    corners = [lambda x, y: x > 0.7 and y < 0.4, lambda x, y: x < 0.3 and y < 0.4,
               lambda x, y: x > 0.7 and y > 0.6, lambda x, y: x < 0.3 and y > 0.6]
    for corner in corners:
        picks = [max(hits, key=lambda f: f[2]) for faces in per_frame
                 if (hits := [f for f in faces if corner(f[0], f[1]) and f[2] < 0.12])]
        if len(picks) < 0.5 * len(per_frame):
            continue
        # Подкаст, интервю: човекът в края на общия кадър също стои на едно място — но до него в
        # същите кадри има и друг човек с лице с подобен размер. Под камерата на стриймър има игра.
        together = sum(1 for faces in per_frame
                       if (hits := [f for f in faces if corner(f[0], f[1]) and f[2] < 0.12])
                       and any(not corner(f[0], f[1]) and f[2] >= 0.6 * max(h[2] for h in hits) for f in faces))
        if together >= 0.3 * len(picks):
            continue
        xs, ys, sizes = (np.array(v) for v in zip(*picks))
        if xs.std() < 0.06 and ys.std() < 0.08:  # мърда в рамката на камерата, не из цялата игра
            return float(np.median(xs)), float(np.median(ys)), float(np.median(sizes))
    return None


def _reframe(folder: Path, segment: Path, offset: float, length: float, bars: str) -> tuple[str, str] | None:
    """Кадриране по лицата. Връща (филтър, описание) или None:
      - клип с хора — цял вертикален екран, който следва лицето във всяка сцена;
      - геймърски клип с камера в ъгъла — камерата горе, играта отдолу („стрийм“);
      - None — лица почти няма или са далечни (игри, анимация, публика) или клипът вече е
        вертикален: тогава целият кадър остава върху замъглен фон."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    model = Path(config.FACE_MODEL)
    size = _video_size(folder, segment)
    if not model.exists() or not size:
        return None
    width, height = size
    if bars:
        width, height = map(int, re.match(r"crop=(\d+):(\d+)", bars).groups())
    crop_w = int(height * 9 / 16) // 2 * 2
    if crop_w >= width * 0.9:
        return None  # вертикален или почти квадратен — няма какво да се реже
    sample_h = int(round(SAMPLE_WIDTH * height / width / 2)) * 2
    raw = _run([ffmpeg(), "-v", "error", "-ss", f"{offset:.2f}", "-t", f"{length:.2f}", "-i", segment.name,
                "-vf", f"{bars}fps={SAMPLE_FPS},scale={SAMPLE_WIDTH}:{sample_h}", "-f", "rawvideo",
                "-pix_fmt", "bgr24", "-"], timeout=300, cwd=folder)
    frame_bytes = SAMPLE_WIDTH * sample_h * 3
    frames = np.frombuffer(raw, np.uint8)[:len(raw) // frame_bytes * frame_bytes].reshape(-1, sample_h, SAMPLE_WIDTH, 3)
    if not len(frames):
        return None
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except AttributeError:
        pass
    detector = cv2.FaceDetectorYN.create(str(model), "", (SAMPLE_WIDTH, sample_h), 0.75)
    centers: list[float | None] = []
    found: list[tuple[float, float, float]] = []   # най-голямото лице: (x, y на центъра, ширина) — част от кадъра
    per_frame: list[list[tuple[float, float, float]]] = []  # всички лица във всеки кадър
    for frame in frames:
        _, faces = detector.detect(frame)
        faces = [] if faces is None else list(faces)
        per_frame.append([(float(f[0] + f[2] / 2) / SAMPLE_WIDTH, float(f[1] + f[3] / 2) / sample_h,
                           float(f[2]) / SAMPLE_WIDTH) for f in faces])
        if not faces:
            centers.append(None)
            continue
        biggest = max(faces, key=lambda f: f[2] * f[3])  # говорещият обикновено е най-близо
        centers.append(float(biggest[0] + biggest[2] / 2) / SAMPLE_WIDTH)
        found.append((centers[-1], float(biggest[1] + biggest[3] / 2) / sample_h, float(biggest[2]) / SAMPLE_WIDTH))
    camera = _corner_camera(per_frame)
    if camera:
        return _stream_layout(width, height, *camera), "стрийм: камерата горе, играта отдолу"
    if found and float(np.median([f[2] for f in found])) < 0.05:
        return None  # лицата са далечни (публика, общ план) — по-добре целият кадър

    def frame_x(center: float) -> float:
        return min(max(center * width - crop_w / 2, 0.0), float(width - crop_w))

    cuts = [c for c in _scene_cuts(folder, segment, offset, length, bars) if 0.3 < c < length - 0.3]
    bounds = [0.0, *cuts, length]
    keys: list[tuple[float, float, bool]] = []
    covered, last_x = 0.0, (width - crop_w) / 2
    for a, b in zip(bounds, bounds[1:]):
        samples = [i for i in range(len(centers)) if a <= i / SAMPLE_FPS < b]
        seen = [(i / SAMPLE_FPS, frame_x(centers[i])) for i in samples if centers[i] is not None]
        if not samples or len(seen) < 0.4 * len(samples):
            keys.append((a, last_x, True))  # сцена без лице — рамката остава, където е била
            continue
        covered += b - a
        # Двама души в общ план: лицата са на две места. Средата между тях е празна стена —
        # рамката остава на едното (което се вижда по-често).
        ordered = sorted(x for _, x in seen)
        gaps = [(ordered[i + 1] - ordered[i], i) for i in range(len(ordered) - 1)]
        if gaps and max(gaps)[0] > 0.2 * width:
            split = ordered[max(gaps)[1]]
            left = [p for p in seen if p[1] <= split]
            right = [p for p in seen if p[1] > split]
            seen = left if len(left) >= len(right) else right
        xs = [x for _, x in seen]
        if max(xs) - min(xs) < 0.08 * width:  # човекът стои — неподвижен кадър
            last_x = float(np.median(xs))
            keys.append((a, last_x, True))
            continue
        # Движи се — ключ на всеки 1.5 секунди (медиана), рамката плавно го следва.
        steps = max(1, int((b - a) / 1.5))
        for k in range(steps):
            t0 = a + k * (b - a) / steps
            window = [x for t, x in seen if t0 <= t < t0 + (b - a) / steps] or [last_x]
            last_x = float(np.median(window))
            keys.append((t0, last_x, k == 0))
    if covered < 0.6 * length:
        return None
    return (f"crop=w={crop_w}:h={height}:x='{_x_expression(keys)}':y=0,"
            f"scale={WIDTH}:{HEIGHT}:flags=lanczos,setsar=1"), "цял екран, кадрирано по лицата"


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def _ass_text(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def subtitles_ass(words: list[Word], length: float, title: str) -> str:
    """Субтитри за рийла: по 2–3 думи, текущата дума — жълта и леко по-голяма (стилът на Shorts),
    заглавието — горе в първите секунди."""
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {HEIGHT}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        # Долу, но над бутоните на YouTube Shorts (~400 px отдолу).
        "Style: Caption,Arial,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,7,3,2,70,70,560,1",
        "Style: Title,Arial,60,&H00FFFFFF,&H00FFFFFF,&H64000000,&H64000000,-1,0,0,0,100,100,0,0,3,20,0,8,80,80,170,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if title:
        wrapped = _wrap(_ass_text(title), 24, 2)
        lines.append(f"Dialogue: 1,{_ass_time(0.2)},{_ass_time(min(4.0, length))},Title,,0,0,0,,"
                     f"{{\\fad(250,350)}}{wrapped}")
    words = [(w, s, e) for w, s, e in words if e > 0 and s < length]
    chunks: list[list[Word]] = []
    for word in words:
        last = chunks[-1] if chunks else None
        if (last and len(last) < 3 and len(" ".join(w for w, _, _ in last + [word])) <= 22
                and word[1] - last[-1][2] < 0.6):
            last.append(word)
        else:
            chunks.append([word])
    for index, chunk in enumerate(chunks):
        following = chunks[index + 1][0][1] if index + 1 < len(chunks) else length
        chunk_end = min(following, chunk[-1][2] + 0.35, length)
        for i, (_, start, _) in enumerate(chunk):
            end = chunk[i + 1][1] if i + 1 < len(chunk) else chunk_end
            text = " ".join((r"{\c&H00D7FF&\fscx112\fscy112}" + _ass_text(w) + r"{\r}") if j == i else _ass_text(w)
                            for j, (w, _, _) in enumerate(chunk))
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(max(end, start + 0.05))},Caption,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def _wrap(text: str, width: int, max_lines: int) -> str:
    words, rows = text.split(), [""]
    for word in words:
        if rows[-1] and len(rows[-1]) + 1 + len(word) > width:
            if len(rows) == max_lines:
                rows[-1] = rows[-1].rstrip(" .,") + "…"
                break
            rows.append(word)
        else:
            rows[-1] = f"{rows[-1]} {word}".strip()
    return r"\N".join(rows)


def _fonts(folder: Path) -> None:
    """Шрифтът за субтитрите — до файловете, за да го намери ffmpeg (с кирилица)."""
    fonts = folder / "fonts"
    fonts.mkdir(exist_ok=True)
    for name in ("arial.ttf", "arialbd.ttf"):
        source = Path(r"C:\Windows\Fonts") / name
        if source.exists() and not (fonts / name).exists():
            shutil.copy2(source, fonts / name)


def _render(folder: Path, segment: Path, offset: float, length: float, subtitles: Path | None, out: Path) -> str:
    """Вертикално 1080×1920. С хора — кадрирано по лицата на цял екран; иначе — целият кадър
    в средата върху същия, увеличен и замъглен. Звукът — до -14 LUFS (нивото на YouTube).
    Кодира на видеокартата (NVENC), иначе на процесора. Връща какво кадриране е избрано."""
    bars = _black_bars(folder, segment, offset + length / 2)
    try:
        reframe = _reframe(folder, segment, offset, length, bars)
    except Exception as e:  # noqa: BLE001 — без кадриране рийлът пак става
        print(f"[Рийлове] Кадриране: {e}")
        reframe = None
    if reframe:
        graph, layout = f"[0:v]{bars}{reframe[0]}", reframe[1]
    else:
        graph = (f"[0:v]{bars}split=2[a][b];"
                 f"[a]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
                 f"boxblur=24:2,eq=brightness=-0.12[bg];"
                 f"[b]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
        layout = "целият кадър върху замъглен фон"
    if subtitles:
        graph += f",ass={subtitles.name}:fontsdir=fonts"  # относителни пътища: „C:“ чупи филтъра
    graph += ",format=yuv420p[v]"
    # aresample: звукът започва точно от 0 като картината (ако в клипа започва по-късно — с тишина
    # отпред) и следва часовете си — иначе някои плейъри го пускат по-рано от картината.
    audio = (f"aresample=async=1:first_pts=0,afade=t=in:d=0.15,afade=t=out:st={max(0.0, length - 0.35):.2f}:d=0.35,"
             f"loudnorm=I=-14:TP=-1.5:LRA=11")
    base = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{offset:.2f}", "-t", f"{length:.2f}",
            "-i", segment.name, "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0?", "-af", audio,
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    problem = None
    limit = ["-maxrate", "12M", "-bufsize", "24M"]  # препоръката на YouTube за 1080p; ~45 MB за 30 с
    for codec in (["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-b:v", "0", *limit],
                  ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", *limit]):
        try:
            _run(base + codec + ["-movflags", "+faststart", out.name], timeout=1800, cwd=folder)
            return layout
        except ReelError as e:
            problem = e
    raise problem


def _texts(info: dict, moment: Moment, spoken: str) -> tuple[str, list[str]]:
    """Заглавие и хаштагове, когато редакторът не ги е написал (напр. откъс без реч)."""
    fallback = moment.chapter or info.get("title") or ""
    prompt = (f"Клип от YouTube: „{info.get('title')}“ (канал {info.get('channel') or info.get('uploader')}).\n"
              f"Откъс {clock(moment.start)}–{clock(moment.end)}"
              + (f", глава „{moment.chapter}“" if moment.chapter else "") + ".\n"
              + (f"Какво се казва в откъса: „{spoken[:1500]}“\n" if spoken else "")
              + (f"Защо е интересен: {', '.join(moment.reasons)}.\n" if moment.reasons else "")
              + f"Напиши за този откъс като YouTube Shorts кратко, закачливо заглавие (до 60 знака, без кавички "
              f"и без хаштагове) и отделно 4 хаштага — на {_language(info, moment)} (имената остават "
              "както са). Отговори САМО с JSON: "
              '{"title": "...", "hashtags": ["#...", "#..."]}')
    return _title_and_tags(_ask_model(prompt, 0.7), fallback)


def make_reel(info: dict, moment: Moment, number: int, folder: Path, subtitles: bool = False) -> dict:
    """Един рийл: тегли откъса, кадрира го, прави корица. Субтитри и заглавие — само ако са поискани."""
    start = max(0.0, moment.start - MARGIN)
    length = moment.end - moment.start
    segment = folder / f"_откъс_{number}.mkv"
    try:
        _grab(info, start, moment.end + 1, segment)
        offset = max(0.0, moment.start - _start(folder, segment))  # откъсът почти винаги започва преди `start`
        # Вече преслушан при избора — думите се пренасят към рийла. Автоматичните субтитри на YouTube
        # са без главни букви и препинателни знаци, затова в самия рийл ги пише Whisper.
        if moment.transcribed and (moment.source != "auto" or not subtitles):
            language = moment.language
            words = [(w, s - moment.start, e - moment.start) for w, s, e in moment.words
                     if s >= moment.start - 0.05 and s < moment.end]
        else:
            language, words = _transcript(segment, offset, length) if subtitles else ("", [])
            if len(words) < 3 and moment.source == "auto":  # Whisper не чу нищо — остават тези на YouTube
                language = moment.language
                words = [(w, s - moment.start, e - moment.start) for w, s, e in moment.words
                         if s >= moment.start - 0.05 and s < moment.end]
        if len(words) < 3 or _looped(words):  # „думи“ в музика или шум — Whisper си ги е измислил
            words = []
        spoken = " ".join(w for w, _, _ in words)
        title, hashtags = (moment.title, moment.hashtags) if moment.title else _texts(info, moment, spoken)
        ass = None
        if subtitles:
            ass = folder / f"_субтитри_{number}.ass"
            ass.write_text(subtitles_ass(words, length, title), encoding="utf-8")
        out = folder / f"рийл {number} ({clock(moment.start).replace(':', '.')}).mp4"
        layout = _render(folder, segment, offset, length, ass, out)
        cover = folder / f"корица {number}.jpg"
        try:  # кадър за миниатюра в YouTube (със заглавието, ако има текст)
            _run([ffmpeg(), "-v", "error", "-y", "-ss", f"{min(1.5, length / 2):.2f}", "-i", out.name,
                  "-frames:v", "1", "-q:v", "3", cover.name], timeout=120, cwd=folder)
        except ReelError:
            cover = None
        return {"file": out, "language": language, "spoken": spoken, "title": title, "hashtags": hashtags,
                "layout": layout, "cover": cover, "length": length}
    finally:
        segment.unlink(missing_ok=True)
        for leftover in folder.glob(f"_субтитри_{number}.ass"):
            leftover.unlink(missing_ok=True)


# =====================================================================================
#  Фонова работа
# =====================================================================================
@dataclass
class Job:
    url: str
    count: int
    seconds: int
    subtitles: bool
    title: str = ""
    stage: str = "започвам"
    done: int = 0
    total: int = 0
    folder: Path | None = None
    error: str = ""
    finished: bool = False
    chosen: str = ""            # защо Орион сам е избрал клипа („Рийл“)
    started: float = field(default_factory=time.time)


# Етапът се казва на глас на български („как вървят рийловете“), а индикаторът в прозореца е на английски.
_CHIP_TEXT = [(r"слушам момент (.+)", r"listening to moment \1"), (r"редакторът гледа момент (.+)", r"editor · moment \1"),
              (r"търся клип: (.+)", r"searching · \1"), (r"избирам клип", "choosing a clip"),
              (r"чета клипа и коментарите", "reading the video and comments"), (r"режа рийл (.+)", r"cutting reel \1")]


def _state(text: str, active: bool = True) -> None:
    if current:
        current.stage = text
    chip = next((re.sub(pattern, english, text) for pattern, english in _CHIP_TEXT if re.fullmatch(pattern, text)), text)
    try:
        state({"active": active, "text": chip})
    except Exception:  # noqa: BLE001 — прозорецът може да е затворен
        pass


def start(url: str, count: int = config.REEL_COUNT, seconds: int = config.REEL_SECONDS,
          subtitles: bool = config.REEL_SUBTITLES) -> str:
    """Започва рийловете във фонов режим. Връща какво да каже Орион веднага."""
    global current, last_url
    count, seconds = max(1, min(int(count), 10)), max(10, min(int(seconds), 180))
    if config.REEL_FREE_ONLY:  # лицензът се проверява веднага — сър разбира още сега, а не след минути
        try:
            ok, why = license_check(fetch(url, comments=False))
        except ReelError as e:
            return f"Не успях да отворя клипа, сър: {e}."
        if not ok:
            last_url = url
            _save_last()
            return (f"Не правя рийлове от този клип, сър: {why}. Правя само от клипове, които авторът е пуснал "
                    f"свободно (Creative Commons). Кажете „намери видеа без авторски права за …“ и ще потърся.")
    with _lock:
        if current and not current.finished:
            return (f"Вече правя рийлове от „{current.title or current.url}“ ({current.stage}), сър. "
                    f"Ще Ви кажа, когато са готови.")
        config.REELS_DIR.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(config.REELS_DIR).free / 2**30
        if free < MIN_FREE_GB:
            return f"На диска с рийловете са свободни само {free:.1f} GB, сър — трябват поне {MIN_FREE_GB}."
        current = Job(url, count, seconds, subtitles)
        last_url = url
        _save_last()
    threading.Thread(target=_work, args=(current,), daemon=True, name="reels").start()
    return (f"Започнах, сър: анализирам клипа, коментарите и какво се казва, и ще изрежа до {count} "
            f"{'рийл' if count == 1 else 'рийла'} около {seconds} секунди. Отнема няколко минути — "
            f"ще Ви кажа, когато са готови.")


# =====================================================================================
#  „Рийл“ — Орион сам избира свободен клип, от който рийловете могат да съберат много гледания
# =====================================================================================
USED_FILE = config.BASE_DIR / "memory" / "reels_used.json"   # клипове, от които вече има рийлове; последните теми

PRODUCER_PROMPT = """Ти си продуцент на YouTube Shorts. Избери ЕДИН клип, от който да изрежем рийлове, които ще
съберат много гледания. Всички кандидати са свободни за ползване (Creative Commons):
{listing}

Избери клипа с най-голям шанс: тема, която интересува много хора; силни моменти, разбираеми без останалата част
(реакции, изненади, интересни факти, емоция); жив говор или зрелищна картина. Гледанията и харесванията показват
интереса към клипа. Отговори САМО с JSON: {{"number": номер, "why": "защо този, до 15 думи, на български"}}"""


def _used() -> dict:
    try:
        data = json.loads(USED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"videos": list(data.get("videos") or []), "topics": list(data.get("topics") or [])}


def _remember_used(video_id: str = "", topics: list[str] | tuple = ()) -> None:
    data = _used()
    if video_id and video_id not in data["videos"]:
        data["videos"] = (data["videos"] + [video_id])[-500:]
    data["topics"] = (data["topics"] + list(topics))[-20:]
    USED_FILE.parent.mkdir(parents=True, exist_ok=True)
    USED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def viral_score(video: dict) -> float:
    """0–1: колко интерес има към самия клип — оттам и шансът рийловете от него да се гледат."""
    import datetime
    views = max(1, video.get("views") or 0)
    days = 365
    try:
        days = max(1, (datetime.date.today() - datetime.datetime.strptime(video["uploaded"], "%Y%m%d").date()).days)
    except (KeyError, TypeError, ValueError):
        pass
    duration = video.get("duration") or 0
    fit = 1.0 if 180 <= duration <= 3600 else 0.6 if 60 <= duration <= 2 * 3600 else 0.2  # има от какво да се реже
    return (0.35 * min(1.0, math.log10(views) / 7)                       # 10 млн. гледания = 1
            + 0.25 * min(1.0, math.log10(views / days + 1) / 4)          # 10 хил. гледания на ден = 1
            + 0.15 * min(1.0, (video.get("likes") or 0) / views / 0.04)  # 4% харесвания = 1
            + 0.15 * (1.0 if video.get("heatmap") else 0.0)              # „най-гледани моменти“ — само при интерес
            + 0.10 * fit)


def _views_words(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} млн.".replace(".0 ", " ").replace(".", ",", 1)
    return f"{round(n / 1000)} хил." if n >= 1000 else str(n)


def choose_video(topic: str = "") -> tuple[dict, str]:
    """Избира клип: търси свободни клипове (по темата или по няколко теми от config.REEL_TOPICS, които не са
    ползвани наскоро), подрежда ги по интереса към тях, а езиковият модел — като продуцент — избира един.
    Клипове, от които вече има рийлове, се пропускат. Връща (клипа, защо)."""
    used = _used()
    if topic:
        topics = [topic]
    else:
        recent = set(used["topics"][-max(1, len(config.REEL_TOPICS) // 2):])
        fresh = [t for t in config.REEL_TOPICS if t not in recent] or list(config.REEL_TOPICS)
        topics = random.sample(fresh, min(3, len(fresh)))
    exclude = set(used["videos"])
    candidates: dict[str, dict] = {}
    for theme in topics:
        _state(f"търся клип: {theme}")
        try:
            found, _ = find_free(theme, 6 if topic else 4, remember=False, exclude=exclude)
        except ReelError as e:
            print(f"[Рийлове] Търсене „{theme}“: {e}")
            continue
        for video in found:
            # Готов шорт не става на нов рийл (и YouTube го смята за повторно качено съдържание).
            if video["duration"] >= 120 and "#short" not in video["title"].lower():
                candidates.setdefault(video["id"], {**video, "topic": theme})
    _remember_used(topics=topics)
    if not candidates:
        raise ReelError(f"не намерих нов свободен клип{f' за „{topic}“' if topic else ''} без риск за авторските права "
                        f"— опитайте с тема, напр. „рийл за космоса“")
    ranked = sorted(candidates.values(), key=viral_score, reverse=True)[:6]
    number = lambda n: f"{n:,}".replace(",", " ")  # noqa: E731 — 1 234 567
    listing = "\n".join(f"{i}. „{v['title']}“ — канал {v['channel']}, тема „{v['topic']}“, {clock(v['duration'])}, "
                        f"{number(v['views'])} гледания, {number(v['likes'])} харесвания"
                        for i, v in enumerate(ranked, 1))
    _state("избирам клип")
    data = _ask_model(PRODUCER_PROMPT.format(listing=listing), 0.4) or {}
    try:
        pick = int(data.get("number")) - 1
    except (TypeError, ValueError):
        pick = 0
    if not 0 <= pick < len(ranked):
        pick = 0
    why = str(data.get("why") or "").strip(" .") or "най-голям интерес сред свободните клипове"
    return ranked[pick], why


def start_auto(topic: str = "", count: int = config.REEL_COUNT, seconds: int = config.REEL_SECONDS,
               subtitles: bool = config.REEL_SUBTITLES) -> str:
    """„Рийл“: Орион сам избира клипа и прави рийловете във фонов режим. Връща какво да каже веднага."""
    global current
    count, seconds = max(1, min(int(count), 10)), max(10, min(int(seconds), 180))
    with _lock:
        if current and not current.finished:
            return (f"Вече правя рийлове от „{current.title or current.url or 'избрания клип'}“ ({current.stage}), сър. "
                    f"Ще Ви кажа, когато са готови.")
        config.REELS_DIR.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(config.REELS_DIR).free / 2**30
        if free < MIN_FREE_GB:
            return f"На диска с рийловете са свободни само {free:.1f} GB, сър — трябват поне {MIN_FREE_GB}."
        current = Job("", count, seconds, subtitles, stage="избирам клип")
    threading.Thread(target=_auto_work, args=(current, topic), daemon=True, name="reels").start()
    return (f"Добре, сър — сам ще избера свободен клип{f' за „{topic}“' if topic else ''}, от който рийловете могат "
            f"да съберат много гледания, и ще ги изрежа. Ще Ви кажа какво съм избрал.")


def _auto_work(job: Job, topic: str) -> None:
    global last_url
    try:
        _state("избирам клип")
        progress("Сам избирам клип: търся свободни клипове" + (f" за „{topic}“" if topic else " по няколко теми")
                 + " и гледам кой има най-голям шанс за много гледания…")
        video, why = choose_video(topic)
    except Exception as e:  # noqa: BLE001 — грешката се казва на сър, работата приключва
        if not isinstance(e, ReelError):
            traceback.print_exc()
        job.error = str(e)
        job.finished = True
        _state("", active=False)
        notify(f"Не успях да избера клип, сър: {e}.")
        return
    job.url, job.chosen, job.title = video["url"], why, video["title"]
    last_url = video["url"]
    _save_last()
    notify(f"Избрах „{video['title']}“ от {video['channel']} — {_views_words(video['views'])} гледания, свободен "
           f"лиценз. {why[0].upper() + why[1:]}. Започвам рийловете.")
    _work(job)


def _work(job: Job) -> None:
    global last_folder
    try:
        _state("чета клипа и коментарите")
        progress("Чета клипа, най-гледаните моменти и коментарите…")
        info = fetch(job.url)
        job.title = info.get("title") or info.get("id") or job.url
        free, why = license_check(info)
        if config.REEL_FREE_ONLY and not free:
            raise ReelError(f"не правя рийлове от „{job.title}“: {why}")
        moments, notes = select(info, job.count, job.seconds)
        job.total = len(moments)
        progress(describe(info, moments, notes))
        folder = config.REELS_DIR / f"{_safe_name(job.title)} [{info.get('id')}]"
        folder.mkdir(parents=True, exist_ok=True)
        _fonts(folder)
        job.folder = folder
        report = [f"Рийлове от „{job.title}“", f"Източник: {info.get('webpage_url') or job.url}",
                  f"Канал: {info.get('channel') or info.get('uploader') or '—'}",
                  f"Моментите са избрани по: {', '.join(notes)}."]
        if job.chosen:
            views = f"{info.get('view_count') or 0:,}".replace(",", " ")
            report.append(f"Клипа го избра Орион: {job.chosen} ({views} гледания).")
        if free:
            report += [f"Лиценз: {why}.",
                       "Сложете този ред в описанието на всеки рийл в YouTube — лицензът го изисква:",
                       f"    {credit_line(info)}",
                       "Орион провери лиценза, който е избрал авторът, и признаците, че клипът е качен от чужд канал. "
                       "Ако все пак в клипа има чужда музика или кадри, YouTube може да ги разпознае (Content ID) — "
                       "ще го видите в YouTube Studio.", ""]
        else:
            report += ["Качвайте ги само ако клипът е Ваш или имате разрешение от автора.", ""]
        for number, moment in enumerate(moments, 1):
            _state(f"режа рийл {number}/{len(moments)}")
            progress(f"Режа рийл {number} от {len(moments)}: {clock(moment.start)}–{clock(moment.end)}"
                     + (f" — „{moment.hook[:80]}“" if moment.hook else "") + ".")
            reel = make_reel(info, moment, number, folder, job.subtitles)
            job.done = number
            report += [reel["file"].name,
                       f"  В оригинала: {clock(moment.start)}–{clock(moment.end)} ({reel['length']:.0f} с)"
                       + (f", глава „{moment.chapter}“" if moment.chapter else ""),
                       f"  Защо: {', '.join(moment.reasons) or '—'}"]
            if moment.rating:
                report.append(f"  Редакторът: {moment.rating:.0f}/10 — {moment.why or '—'}")
            if moment.hook:
                report.append(f"  Кука (първото изречение): {moment.hook}")
            report += [f"  Кадър: {reel['layout']}", f"  Заглавие: {reel['title']}",
                       f"  Хаштагове: {' '.join(reel['hashtags'])}"]
            if reel["cover"]:
                report.append(f"  Корица: {reel['cover'].name}")
            report += [f"  Текст: {reel['spoken'][:500]}", ""]
            progress(f"Готов рийл {number}: „{reel['title']}“ ({reel['layout']}).")
        (folder / "описание.txt").write_text("\n".join(report), encoding="utf-8")
        last_folder = folder
        _remember_used(info.get("id") or "")  # „Рийл“ няма да избере този клип отново
        minutes = max(1, round((time.time() - job.started) / 60))
        notify(f"Готово, сър: {len(moments)} {'рийл' if len(moments) == 1 else 'рийла'} от „{_safe_name(job.title, 50)}“ "
               f"за {minutes} мин. Заглавията, хаштаговете и кориците са в папката. Кажете „покажи рийловете“, "
               f"за да я отворя.")
    except ReelError as e:
        job.error = str(e)
        notify(f"Не успях да направя рийловете, сър: {e}.")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job.error = f"{type(e).__name__}: {e}"
        notify(f"Рийловете спряха заради техническа грешка, сър ({type(e).__name__}). Подробностите са в журнала.")
    finally:
        job.finished = True
        _state("", active=False)
        from . import speech
        speech.release_cpu_model()
        if job.folder:
            for leftover in job.folder.glob("_*"):
                leftover.unlink(missing_ok=True)
            shutil.rmtree(job.folder / "fonts", ignore_errors=True)


def status() -> str:
    job = current
    if job is None:
        return "В тази сесия още не съм правил рийлове."
    if not job.finished:
        minutes = int((time.time() - job.started) // 60)
        if not job.url:
            return f"Още избирам клип за рийловете: {job.stage} (от {minutes} мин.)."
        return (f"Правя рийлове от „{job.title or job.url}“: {job.stage}"
                + (f", готови {job.done} от {job.total}" if job.total else "") + f" (от {minutes} мин.).")
    if job.error:
        return f"Последният опит не успя: {job.error}."
    return f"Последните рийлове са готови: {job.done} от „{job.title}“ в папка {job.folder}."
