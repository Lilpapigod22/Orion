"""
Връзка с Google (Gmail, Календар, Задачи) през малък скрипт в акаунта на сър.

Скриптът (integrations/google_bridge.gs) работи като уеб приложение в Google Apps Script
и приема само заявки с тайния ключ от google_settings.json. Така не е нужен проект в
Google Cloud, а достъпът не изтича. Настройка: „Митко, свържи Google“ (виж README.md).
"""
import json
import re
import secrets
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "google_settings.json"   # таен ключ + адрес на моста (само на този компютър)
BRIDGE_CODE = BASE_DIR / "integrations" / "google_bridge.gs"
URL_RE = re.compile(r"https://script\.google\.com/(?:a/macros/[\w.\-]+|macros)/s/[\w\-]+/exec")

NOT_CONNECTED = ("Google още не е свързан, сър. Кажете „Митко, свържи Google“ и ще Ви покажа "
                 "как — отнема около пет минути.")


class GoogleError(Exception):
    """Грешка от Google, която сър трябва да чуе (напр. липсваща услуга или изтекъл достъп)."""


def _settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def is_connected() -> bool:
    settings = _settings()
    return bool(settings.get("url") and settings.get("secret"))


def bridge_code() -> str:
    """Кодът на моста с тайния ключ (създава ключа при първо извикване)."""
    settings = _settings()
    if not settings.get("secret"):
        settings["secret"] = secrets.token_urlsafe(32)
        _save(settings)
    return BRIDGE_CODE.read_text(encoding="utf-8").replace("__JARVIS_SECRET__", settings["secret"])


def call(action: str, **params):
    """Изпълнява действие в моста и връща резултата. Хвърля GoogleError при проблем."""
    settings = _settings()
    if not (settings.get("url") and settings.get("secret")):
        raise GoogleError(NOT_CONNECTED)
    body = json.dumps({"secret": settings["secret"], "action": action, "params": params}).encode("utf-8")
    request = urllib.request.Request(settings["url"], data=body, headers={"Content-Type": "application/json"})
    try:
        # Google отговаря с пренасочване; urllib го следва сам (като GET, както Google очаква).
        with urllib.request.urlopen(request, timeout=40) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise GoogleError(f"Google отказа заявката ({e.code}). Проверете дали мостът е публикуван "
                          f"като уеб приложение с достъп „Anyone“.") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GoogleError("Няма връзка с Google — проверете интернета.") from e
    try:
        data = json.loads(raw)
    except ValueError:
        raise GoogleError("Google върна страница за вход вместо данни. При публикуването на моста "
                          "изберете „Who has access: Anyone“.") from None
    if "error" in data:
        error = data["error"]
        if "Tasks is not defined" in error:
            error = "в скрипта липсва услугата „Google Tasks API“ (Services → + → Google Tasks API)"
        elif error == "грешен ключ":
            error = "ключът не съвпада — копирайте кода на моста наново с „Митко, свържи Google“"
        raise GoogleError(f"Google върна грешка: {error}.")
    return data.get("result")


def connect(url: str) -> dict:
    """Запазва адреса на моста и проверява връзката. Връща {email, calendar}."""
    match = URL_RE.search(url)
    if not match:
        raise GoogleError("Това не прилича на адрес на уеб приложение от Google Apps Script "
                          "(трябва да завършва на /exec).")
    settings = _settings()
    if not settings.get("secret"):
        raise GoogleError("Първо кажете „Митко, свържи Google“, за да създам ключа и кода.")
    previous = settings.get("url")
    settings["url"] = match.group(0)
    _save(settings)
    try:
        return call("ping")
    except GoogleError:
        settings["url"] = previous  # Не пазим адрес, който не работи.
        _save(settings)
        raise


SETUP_STEPS = [
    "Отворих script.google.com в браузъра и копирах кода на моста (с Вашия таен ключ).",
    "1. Ако страницата иска вход — влезте в Google акаунта си.",
    "2. Изтрийте кода в редактора (Ctrl+A) и поставете моя (Ctrl+V). Запазете с Ctrl+S.",
    "3. Вляво до „Services“ натиснете „+“, изберете „Google Tasks API“ и натиснете „Add“.",
    "4. Горе вдясно: Deploy → New deployment → зъбното колелце → Web app.",
    "5. Execute as: Me. Who has access: Anyone. Натиснете Deploy.",
    "6. Authorize access → изберете акаунта → Advanced → Go to … (unsafe) → Allow. "
    "Това е Вашият собствен скрипт, затова Google го нарича „непроверен“.",
    "7. Копирайте адреса „Web app URL“ (завършва на /exec) и го поставете тук, в полето отдолу.",
]
