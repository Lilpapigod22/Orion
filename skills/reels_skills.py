"""
Рийлове от YouTube: анализ кои моменти от клип харесват най-много (най-гледани, коментари) и
изрязване на вертикални видеа за YouTube Shorts. Работата е в jarvis/reels.py.
"""
import os

import config
from jarvis import jarvis_tool, reels


def _url(url: str) -> str:
    found = reels.find_url(url) or (url.strip() if url.strip().startswith("http") else "")
    if not found and reels.last_url:
        return reels.last_url  # „направи рийлове“ след анализа — същият клип
    if not found:
        raise ValueError("дайте ми линк към клип от YouTube (youtube.com/watch?v=… или youtu.be/…)")
    return found


@jarvis_tool
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


@jarvis_tool
def make_youtube_reels(url: str = "", count: int = config.REEL_COUNT, seconds: int = config.REEL_SECONDS,
                       subtitles: bool = True) -> str:
    """Прави рийлове (YouTube Shorts) от клип в YouTube: намира най-гледаните и най-коментирани
    моменти, изрязва ги вертикално (9:16) със субтитри и предлага заглавия и хаштагове. Работи във
    фонов режим няколко минути. За „направи рийлове/шортс от този клип“, „изрежи най-хубавите моменти“.

    Args:
        url: Линкът към клипа (празно — последният анализиран клип).
        count: Колко рийла (1–10).
        seconds: Колко секунди да е всеки (10–180; за Shorts обикновено 30–60).
        subtitles: Дали да има субтитри дума по дума.
    """
    return reels.start(_url(url), count, seconds, subtitles)


@jarvis_tool
def reels_status() -> str:
    """Докъде е стигнало правенето на рийлове. За „готови ли са рийловете“, „как върви“."""
    return reels.status()


@jarvis_tool
def show_reels() -> str:
    """Отваря папката с готовите рийлове. За „покажи рийловете“, „отвори папката с шортсовете“."""
    folder = reels.last_folder or config.REELS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    os.startfile(folder)
    return f"Отворих папката „{folder.name}“."
