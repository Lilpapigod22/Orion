"""
Finding and starting programs and websites by name — the way sir says them, in Bulgarian or English.

Orion does not run arbitrary commands: it only starts programs that are installed
(on PATH, in the “App Paths” registry key, or as a shortcut in the Start menu / on the Desktop),
and only opens http(s) addresses.
"""
import difflib
import os
import re
import shutil
import time
import webbrowser
from pathlib import Path

# Name (as sir says it) -> command. Add your own: "name": "command or full path to the .exe".
PROGRAMS = {
    "chrome": "chrome", "google chrome": "chrome", "хром": "chrome", "гугъл хром": "chrome",
    "edge": "msedge", "microsoft edge": "msedge", "едж": "msedge",
    "firefox": "firefox", "файърфокс": "firefox",
    "браузър": "browser", "интернет": "browser",
    "бележник": "notepad", "notepad": "notepad", "нотпад": "notepad",
    "калкулатор": "calc", "calculator": "calc", "calc": "calc",
    "paint": "mspaint", "пейнт": "mspaint",
    "файлове": "explorer", "explorer": "explorer", "папки": "explorer", "моите документи": "explorer",
    "този компютър": "explorer", "моят компютър": "explorer",
    "vscode": "visual studio code", "vs code": "visual studio code", "вс код": "visual studio code",
    "терминал": "wt", "terminal": "wt", "команден ред": "cmd", "cmd": "cmd", "powershell": "powershell",
    "диспечер на задачите": "taskmgr", "task manager": "taskmgr",
    "настройки": "ms-settings:", "settings": "ms-settings:",
    "контролен панел": "control", "control panel": "control",
    "word": "winword", "уърд": "winword", "excel": "excel", "ексел": "excel",
    "powerpoint": "powerpnt", "пауърпойнт": "powerpnt", "outlook": "outlook", "аутлук": "outlook",
}

# How Microsoft Store apps are pronounced -> their name in Start.
STORE_ALIASES = {"клод": "claude", "клауд": "claude", "клаудия": "claude", "ексбокс": "xbox", "иксбокс": "xbox",
                 "пасианс": "solitaire", "уотсап": "whatsapp", "вотсап": "whatsapp"}

# Popular websites -> address. Any name with a dot („abv.bg“) is also taken as a website.
SITES = {
    "youtube": "youtube.com", "ютуб": "youtube.com", "ютюб": "youtube.com",
    "google": "google.com", "гугъл": "google.com",
    "gmail": "mail.google.com", "джимейл": "mail.google.com", "гмейл": "mail.google.com",
    "facebook": "facebook.com", "фейсбук": "facebook.com",
    "instagram": "instagram.com", "инстаграм": "instagram.com",
    "tiktok": "tiktok.com", "тикток": "tiktok.com",
    "netflix": "netflix.com", "нетфликс": "netflix.com",
    "twitch": "twitch.tv", "туич": "twitch.tv",
    "twitter": "x.com", "туитър": "x.com",
    "reddit": "reddit.com", "редит": "reddit.com",
    "wikipedia": "bg.wikipedia.org", "уикипедия": "bg.wikipedia.org",
    "chatgpt": "chatgpt.com", "чат джипити": "chatgpt.com",
    "google maps": "maps.google.com", "гугъл карти": "maps.google.com", "карти": "maps.google.com",
    "abv": "abv.bg", "абв": "abv.bg",
}

# Words sir says before the name: „отвори програмата Steam“, „сайта YouTube“.
_PREFIX_RE = re.compile(r"^(програмата|приложението|апликацията|играта|сайта|сайтът|страницата|уебсайта)\s+",
                        re.IGNORECASE)
_ARTICLES = ("ът", "ят", "та", "то", "те", "а", "я")
_TRANSLIT = dict(zip(
    "абвгдежзийклмнопрстуфхцчшщъьюя",
    ["a", "b", "v", "g", "d", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
     "u", "f", "h", "ts", "ch", "sh", "sht", "a", "y", "yu", "ya"],
))
_SKIP_SHORTCUT = re.compile(r"uninstall|деинстал|readme|help|помощ|license|website|документация", re.IGNORECASE)


def _base(word: str) -> str:
    """„калкулатора“ -> „калкулатор“: removes the article so the different forms match."""
    for suffix in _ARTICLES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def normalize(name: str) -> str:
    name = re.sub(r"[\"'„“”«»!?.,;:]+$|^[\"'„“”«»]+", "", name.strip().lower())
    name = _PREFIX_RE.sub("", name)
    return " ".join(_base(w) for w in name.split())


def to_latin(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in text.lower())


_PROGRAM_KEYS = {normalize(k): v for k, v in PROGRAMS.items()}
_SITE_KEYS = {normalize(k): v for k, v in SITES.items()}


# --- Lookup ---------------------------------------------------------------------------------
def _app_path(exe: str) -> str | None:
    """The full path of a program registered in Windows (“App Paths” — e.g. chrome, winword)."""
    if os.name != "nt":
        return None
    import winreg
    exe = exe if exe.lower().endswith(".exe") else exe + ".exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            path = winreg.QueryValue(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}")
        except OSError:
            continue
        path = path.strip('"')
        if path and os.path.isfile(path):
            return path
    return None


def _resolve_command(command: str) -> str | None:
    if command.endswith(":"):  # ms-settings: and similar Windows addresses
        return command
    if os.path.isabs(command):
        return command if os.path.isfile(command) else None
    return shutil.which(command) or _app_path(command)


def _shortcut_files():
    env = os.environ.get
    for root in (env("APPDATA", ""), env("PROGRAMDATA", r"C:\ProgramData")):
        yield from (Path(root) / "Microsoft/Windows/Start Menu/Programs").rglob("*")
    # The Desktop — only the top level (that is where the games are), no sub-folders.
    for desktop in (Path.home() / "Desktop", Path(env("PUBLIC", r"C:\Users\Public")) / "Desktop"):
        if desktop.is_dir():
            yield from desktop.iterdir()


_shortcut_cache: tuple[float, dict[str, Path]] = (-1e9, {})


def _shortcuts() -> dict[str, Path]:
    """Shortcut name (lower case) -> file. Refreshed every minute: programs change."""
    global _shortcut_cache
    if time.monotonic() - _shortcut_cache[0] > 60:
        found: dict[str, Path] = {}
        for path in _shortcut_files():
            if path.suffix.lower() in (".lnk", ".url") and not _SKIP_SHORTCUT.search(path.stem):
                found.setdefault(path.stem.lower(), path)
        _shortcut_cache = (time.monotonic(), found)
    return _shortcut_cache[1]


_start_apps_cache: tuple[float, dict[str, str]] = (-1e9, {})


def _start_apps() -> dict[str, str]:
    """Name (lower case) -> AppID of all apps in Start, including Microsoft Store ones
    (Claude, Spotify, Xbox) that have no ordinary shortcut. Refreshed every 10 minutes."""
    global _start_apps_cache
    if time.monotonic() - _start_apps_cache[0] > 600:
        found = {}
        try:
            import json
            import subprocess
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for app in json.loads(result.stdout.decode("utf-8") or "[]"):
                if app.get("Name") and app.get("AppID") and not _SKIP_SHORTCUT.search(app["Name"]):
                    found.setdefault(app["Name"].lower(), app["AppID"])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        _start_apps_cache = (time.monotonic(), found)
    return _start_apps_cache[1]


def _match_shortcut(query: str, fuzzy: bool, shortcuts: dict | None = None) -> tuple[str, Path] | None:
    """The best-matching shortcut. Without `fuzzy` — only an exact name or the start of a name."""
    shortcuts = _shortcuts() if shortcuts is None else shortcuts
    if len(query) < 3 or not shortcuts:
        return None
    latin = to_latin(query)
    # „стийм“ -> stiym -> steem, „вайбър“ -> vaybar -> vibar: closer to English spelling.
    variants = {query, latin, latin.replace("iy", "ee").replace("ay", "i")}
    best, best_score = None, 0.0
    for name, path in shortcuts.items():
        words = re.split(r"[\s\-_]+", name)
        for q in variants:
            if name == q:
                score = 1.0
            elif name.startswith(q + " ") or q in words:
                score = 0.95
            elif not fuzzy:
                continue
            elif q in name:
                score = 0.9
            else:
                score = max(difflib.SequenceMatcher(None, q, w).ratio() for w in [name, *words])
            # On a tie the shorter name wins („Steam“ over „Steam VR Tutorial“).
            if score > best_score or (score == best_score and best and len(name) < len(best[0])):
                best, best_score = (name, path), score
    return best if best and best_score >= 0.8 else None


def find_program(name: str, fuzzy: bool = True) -> tuple[str, str] | None:
    """(display name, command or path) of an installed program, or None."""
    query = normalize(name)
    if not query:
        return None
    title = _PREFIX_RE.sub("", name.strip())
    command = _PROGRAM_KEYS.get(query)
    if command == "browser":
        return title, "browser"
    if command:
        # A command („chrome“) or a Start menu shortcut name („visual studio code“).
        shortcut = None if _resolve_command(command) else _match_shortcut(command, fuzzy=False)
        target = _resolve_command(command) or (str(shortcut[1]) if shortcut else None)
        if target:
            return title, target
    # Steam/Riot/Epic games — by their names („лол“, „апекс“, „хой“), before shortcuts.
    from . import games
    game = games.find(name)
    if game:
        return game.name, "game"
    shortcut = _match_shortcut(query, fuzzy)
    if shortcut:
        return shortcut[1].stem, str(shortcut[1])
    # Microsoft Store apps (Claude, Spotify, Xbox…) — started through shell:AppsFolder.
    start_apps = _start_apps()
    app = _match_shortcut(STORE_ALIASES.get(query, query), fuzzy, start_apps)
    if app:
        title = next(n for n in start_apps if n == app[0])
        return title.title() if title.islower() else title, f"shell:AppsFolder\\{app[1]}"
    return None


def find_site(name: str) -> str | None:
    """The full address of a website by name („ютуб“ -> https://youtube.com) or None."""
    raw = _PREFIX_RE.sub("", name.strip().strip("\"'„“”«»").rstrip(".!?"))
    if re.fullmatch(r"https?://\S+", raw, re.IGNORECASE):
        return raw
    if re.fullmatch(r"(www\.)?[\w\-]+(\.[\w\-]+)+(/\S*)?", raw):
        return "https://" + raw
    site = _SITE_KEYS.get(normalize(name))
    return f"https://{site}" if site else None


# --- Starting ---------------------------------------------------------------------------------
def open_program(name: str) -> str:
    """Starts a program by name. Raises FileNotFoundError if it is not installed."""
    found = find_program(name)
    if not found:
        raise FileNotFoundError(f"не намирам програма „{name}“ на този компютър")
    title, target = found
    if target == "browser":
        webbrowser.open("https://www.google.com")
    elif target == "game":
        from . import games
        games.launch(games.find(name))
        return f"Пускам {title}."
    else:
        os.startfile(target)  # noqa: S606 — only found, installed programs
    return f"Стартирах {title}."


def open_site(url_or_name: str) -> str:
    """Opens a website in the browser. Accepts an address („abv.bg“) or a name („ютуб“)."""
    url = find_site(url_or_name)
    if not url:
        raise ValueError(f"„{url_or_name}“ не е адрес на сайт")
    webbrowser.open(url)
    return f"Отворих {url}."
