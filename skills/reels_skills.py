"""
Рийлове от YouTube: анализ кои моменти от клип харесват най-много (най-гледани, коментари) и
изрязване на вертикални видеа за YouTube Shorts. Работата е в orion/reels.py.
"""
import os
import re

import config
from orion import orion_tool, reels


def _url(url: str) -> str:
    found = reels.pick_found(url) or reels.find_url(url) or (url.strip() if url.strip().startswith("http") else "")
    if not found and re.fullmatch(r"\s*(?:номер\s*|№\s*|#)?\d{1,2}\s*", url or ""):
        raise ValueError("няма списък с клипове, от който да избера този номер")  # -> Орион сам избира
    if not found and reels.last_url:
        return reels.last_url  # „направи рийлове“ след анализа — същият клип
    if not found:
        raise ValueError("дайте ми линк към клип от YouTube (youtube.com/watch?v=… или youtu.be/…)")
    return found


@orion_tool
def analyze_youtube_video(url: str, count: int = 5) -> str:
    """Анализира клип от YouTube: кои моменти зрителите гледат най-много и за кои пишат в
    коментарите. За „анализирай този клип“, „кое е най-интересното в това видео“.

    Args:
        url: Линкът към клипа (празно — последният клип).
        count: Колко от най-силните моменти да изброи.
    """
    try:
        return reels.analyze_url(_url(url), max(1, min(count, 10)))
    except reels.ReelError as e:
        raise ValueError(str(e)) from e


@orion_tool
def make_youtube_reels(url: str = "", count: int = config.REEL_COUNT, seconds: int = config.REEL_SECONDS,
                       subtitles: bool = config.REEL_SUBTITLES) -> str:
    """Прави рийлове (YouTube Shorts) от клип в YouTube: намира най-гледаните и най-коментирани
    моменти, изрязва ги вертикално (9:16) — само картината и звукът, без текст върху видеото, звукът
    съвпада точно с картината — и предлага заглавия и хаштагове. Работи във фонов режим няколко минути.
    Само от клипове, които авторът е пуснал свободно (лиценз Creative Commons) — другите отказва.
    За „направи рийлове/шортс от този клип“, „изрежи най-хубавите моменти“, „направи рийлове от номер 2“.

    Args:
        url: Линкът към клипа или номерът от последното търсене на свободни клипове („2“); празно — последният клип.
        count: Колко рийла (1–10).
        seconds: Колко секунди да е всеки (10–180; за Shorts обикновено 30–60).
        subtitles: Субтитри и заглавие върху видеото — True само ако сър изрично ги поиска.
    """
    try:
        chosen = _url(url)
    except ValueError:  # няма линк (или списъкът с номера е от отдавна) — Орион сам избира клипа
        return reels.start_auto("", count, seconds, subtitles)
    return reels.start(chosen, count, seconds, subtitles)


@orion_tool
def auto_reels(topic: str = "", count: int = config.REEL_COUNT, seconds: int = config.REEL_SECONDS) -> str:
    """Орион сам избира свободен клип (Creative Commons), от който рийловете могат да съберат много гледания —
    по интереса към клипа и по своя преценка като продуцент — и прави рийловете. Работи във фонов режим.
    За „рийл“, „направи рийл сам“, „избери ти клип и направи рийлове“, „рийл за космоса“.

    Args:
        topic: Тема, ако сър е казал (напр. „космос“); празно — Орион избира и темата.
        count: Колко рийла (1–10).
        seconds: Колко секунди да е всеки (10–180).
    """
    return reels.start_auto(topic, count, seconds)


@orion_tool
def find_free_videos(topic: str, count: int = 5) -> str:
    """Търси в YouTube клипове по тема, които авторите са пуснали свободно (лиценз Creative Commons —
    позволено е да се ползват, и за рийлове, с посочване на автора), и проверява всеки, че не е качен от
    чужд канал. За „намери видеа без авторски права за …“, „свободни клипове за рийлове“, „видеа без копирайт“.

    Args:
        topic: За какво да са клиповете (напр. „космос“, „funny cats“).
        count: Колко клипа да намери (1–10).
    """
    count = max(1, min(int(count), 10))
    try:
        found, skipped = reels.find_free(topic, count)
    except reels.ReelError as e:
        raise ValueError(str(e)) from e
    # Списъкът с линковете — в журнала; на глас — без линкове.
    lines = [f"Свободни клипове за „{topic}“ (Creative Commons, без признаци, че са чужди):"]
    lines += [f"{i}. „{v['title']}“ — {v['channel']} · {reels.clock(v['duration'])} · {v['url']}"
              for i, v in enumerate(found, 1)]
    if skipped:
        lines.append(f"Пропуснах {len(skipped)} с риск: " + "; ".join(f"„{t[:50]}“ — {why}" for t, why in skipped[:6]))
    reels.progress("\n".join(lines))
    if not found:
        return (f"Не намерих клипове за „{topic}“, които със сигурност са свободни — пропуснах {len(skipped)} "
                f"заради риск за авторските права. Опитайте с друга тема или на английски — там има повече.")
    minutes = lambda v: max(1, round(v["duration"] / 60))  # noqa: E731
    short = lambda title: title if len(title) <= 50 else title[:50].rsplit(" ", 1)[0] + "…"  # noqa: E731
    listed = "; ".join(f"{i}. „{short(v['title'])}“, {minutes(v)} {'минута' if minutes(v) == 1 else 'минути'}"
                       for i, v in enumerate(found[:3], 1))
    more = f" и още {len(found) - 3}" if len(found) > 3 else ""
    return (f"Намерих {len(found)} свободни {'клип' if len(found) == 1 else 'клипа'} за „{topic}“: {listed}{more}. "
            f"Всички са в журнала с линкове. Кажете „направи рийлове от номер 1“.")


@orion_tool
def reels_status() -> str:
    """Докъде е стигнало правенето на рийлове. За „готови ли са рийловете“, „как върви“."""
    return reels.status()


@orion_tool
def show_reels() -> str:
    """Отваря папката с готовите рийлове. За „покажи рийловете“, „отвори папката с шортсовете“."""
    folder = reels.last_folder or config.REELS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    os.startfile(folder)
    return f"Отворих папката „{folder.name}“."
