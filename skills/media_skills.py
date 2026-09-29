"""
Още музика: радиостанции (от целия свят, българските първо), Spotify и музиката на компютъра.
"""
import os
import urllib.parse
import webbrowser

from jarvis import folders, geo, jarvis_tool

RADIO_API = "https://de1.api.radio-browser.info/json/stations"


def _stations(query: str = "", limit: int = 10) -> list[dict]:
    params = {"limit": limit, "hidebroken": "true", "order": "clickcount", "reverse": "true"}
    if query:
        params["name"] = query
    else:
        params["countrycode"] = "BG"
    return geo.get_json(f"{RADIO_API}/search?" + urllib.parse.urlencode(params))


@jarvis_tool
def play_radio(station: str) -> str:
    """Пуска радиостанция онлайн: БНР Хоризонт, Радио 1, N-JOY, Energy, BBC… (и чужди).

    Args:
        station: Името на радиото, напр. "Хоризонт" или "N-JOY".
    """
    found = _stations(station, 10)
    if not found:
        from jarvis.apps import to_latin
        found = _stations(to_latin(station), 10)
    if not found:
        return f"Не намерих радио „{station}“."
    best = next((s for s in found if s.get("countrycode") == "BG"), found[0])
    webbrowser.open(best["url_resolved"] or best["url"])
    return f"Пуснах радио {best['name'].strip()} (спира се от раздела в браузъра)."


@jarvis_tool
def radio_stations() -> str:
    """Най-слушаните български радиостанции онлайн."""
    names = [s["name"].strip() for s in _stations("", 12)]
    return "Популярни радиа: " + ", ".join(dict.fromkeys(names)) + "."


@jarvis_tool
def play_on_spotify(query: str) -> str:
    """Търси песен, изпълнител или плейлист в Spotify (приложението).

    Args:
        query: Какво да потърси, напр. "Coldplay".
    """
    os.startfile("spotify:search:" + urllib.parse.quote(query))
    return f"Отворих „{query}“ в Spotify — натиснете Play на песента, която искате."


@jarvis_tool
def play_local_music(query: str = "") -> str:
    """Пуска музика от компютъра (папка „Музика“) — песен по име или цялата папка.

    Args:
        query: Дума от името на песента (празно — пуска папката).
    """
    music = folders.known().get("музика")
    if not music or not music.is_dir():
        return "Няма папка „Музика“."
    songs = [f for f in music.rglob("*") if f.suffix.lower() in (".mp3", ".flac", ".m4a", ".wav", ".ogg", ".wma")]
    if query:
        songs = [f for f in songs if query.lower() in f.stem.lower()]
    if not songs:
        return f"Не намерих песни{' с „' + query + '“' if query else ''} в папка „Музика“."
    os.startfile(songs[0])
    return f"Пуснах „{songs[0].stem}“" + (f" (от {len(songs)} намерени)." if len(songs) > 1 else ".")
