"""
The games on this computer — from Steam, Riot (League of Legends, VALORANT) and Epic Games.

Found by the names sir uses: „пусни Апекс“, „лол“, „хартс ъф айрън“, „хой“.
Started through their own launcher (steam://, Riot Client, Epic), just like a double-click.
"""
import difflib
import glob
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Game:
    name: str
    source: str               # steam, riot, epic
    launch: str | list[str]   # an address (steam://…) or a command with arguments (Riot)


# How sir says it -> the real name (or part of it). Abbreviations are also recognised automatically.
ALIASES = {
    "лол": "league of legends", "лига": "league of legends", "лигата": "league of legends",
    "лига на легендите": "league of legends", "кс": "counter-strike", "каунтър": "counter-strike",
    "каунтър страйк": "counter-strike", "апекс": "apex legends", "хой": "hearts of iron", "хартс ъф айрън": "hearts of iron",
    "банърлорд": "bannerlord", "маунт енд блейд": "mount & blade", "репо": "r.e.p.o", "ри по": "r.e.p.o",
    "валорант": "valorant", "тфт": "teamfight tactics", "дота": "dota", "гта": "grand theft auto",
    "майнкрафт": "minecraft", "фортнайт": "fortnite", "рунтера": "runeterra",
}
_SKIP = re.compile(r"redistributable|steamworks|soundtrack|dedicated server|\bsdk\b|proton|runtime", re.IGNORECASE)
_RIOT_PRODUCTS = {
    "league_of_legends": ("League of Legends", "League of Legends"),
    "valorant": ("VALORANT", "VALORANT"),
    "bacon": ("Legends of Runeterra", "LoR"),
}
_cache: tuple[float, list[Game]] = (-1e9, [])


def _steam_games() -> list[Game]:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return []
    libraries = {steam}
    try:
        text = (steam / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        libraries |= {Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', text)}
    except OSError:
        pass
    games = []
    for library in libraries:
        for manifest in glob.glob(str(library / "steamapps" / "appmanifest_*.acf")):
            try:
                text = Path(manifest).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            name, appid = re.search(r'"name"\s+"([^"]+)"', text), re.search(r'"appid"\s+"(\d+)"', text)
            if name and appid and not _SKIP.search(name[1]):
                games.append(Game(name[1], "steam", f"steam://rungameid/{appid[1]}"))
    return games


def _riot_games() -> list[Game]:
    try:
        installs = json.loads(Path(r"C:\ProgramData\Riot Games\RiotClientInstalls.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    client = installs.get("rc_default") or installs.get("rc_live")
    if not client or not os.path.isfile(client):
        return []
    metadata = Path(r"C:\ProgramData\Riot Games\Metadata")
    games = []
    for product, (name, folder) in _RIOT_PRODUCTS.items():
        installed = (metadata / f"{product}.live").is_dir() and any(
            Path(root, folder).is_dir() for root in (r"C:\Riot Games", r"D:\Riot Games"))
        if installed:
            games.append(Game(name, "riot", [client, f"--launch-product={product}", "--launch-patchline=live"]))
    return games


def _epic_games() -> list[Game]:
    games = []
    for manifest in glob.glob(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests\*.item"):
        try:
            data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("DisplayName") and data.get("AppName"):
            games.append(Game(data["DisplayName"], "epic",
                              f"com.epicgames.launcher://apps/{data['AppName']}?action=launch&silent=true"))
    return games


def installed() -> list[Game]:
    """All installed games. Refreshed every minute."""
    global _cache
    if time.monotonic() - _cache[0] > 60:
        games = _steam_games() + _riot_games() + _epic_games()
        _cache = (time.monotonic(), sorted(games, key=lambda g: g.name.lower()))
    return _cache[1]


def _initials(name: str) -> str:
    """„Hearts of Iron IV“ -> „hoi“, „League of Legends“ -> „lol“, „Grand Theft Auto V“ -> „gta“."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    return "".join(w[0] for w in words if not re.fullmatch(r"[ivx]+|\d+", w))


def find(query: str) -> Game | None:
    """The game sir means, or None."""
    from .apps import normalize, to_latin
    games = installed()
    if not games:
        return None
    q = normalize(query).strip()
    q = ALIASES.get(q, q)
    latin = to_latin(q).replace("y", "i")
    best, best_score = None, 0.0
    for game in games:
        name = game.name.lower()
        plain = re.sub(r"[^a-z0-9 ]+", " ", name)
        for variant in {q, latin, to_latin(q)}:
            if not variant:
                continue
            if variant in name or variant in plain:
                score = 1.0 if len(variant) >= 3 else 0.7
            elif variant.replace(" ", "") == _initials(game.name):
                score = 0.95
            else:
                score = max(difflib.SequenceMatcher(None, variant, w).ratio()
                            for w in [plain, *plain.split()] if len(w) >= 3) if len(variant) >= 4 else 0
            if score > best_score:
                best, best_score = game, score
    return best if best_score >= 0.78 else None


def launch(game: Game) -> None:
    if isinstance(game.launch, list):
        import subprocess
        subprocess.Popen(game.launch, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        os.startfile(game.launch)  # noqa: S606 — steam:// and com.epicgames.launcher:// addresses
