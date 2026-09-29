"""
Управление на компютъра: звук, музика, състояние на системата, затваряне на програми,
заключване/изключване, снимка на екрана, клипборд, папки и файлове.

Всичко необратимо (затваряне на програма, изключване, рестарт, сън) става само след бутона
в прозореца (jarvis/confirm.py).
"""
import ctypes
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from jarvis import apps, confirm, folders, jarvis_tool

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --- Звук и музика ----------------------------------------------------------------------------
def _endpoint():
    import comtypes
    from pycaw.pycaw import AudioUtilities
    comtypes.CoInitialize()  # всяка нишка, която говори със звуковата система, трябва да го направи
    return AudioUtilities.GetSpeakers().EndpointVolume


def _volume_now(endpoint) -> str:
    level = round(endpoint.GetMasterVolumeLevelScalar() * 100)
    return f"Звукът е на {level}%" + (" (заглушен)." if endpoint.GetMute() else ".")


@jarvis_tool
def set_volume(level: int) -> str:
    """Слага силата на звука на компютъра на точна стойност. За „звукът на 30“, „сложи звука на половина“.

    Args:
        level: От 0 до 100.
    """
    endpoint = _endpoint()
    endpoint.SetMute(0, None)
    endpoint.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)
    return _volume_now(endpoint)


@jarvis_tool
def change_volume(amount: int) -> str:
    """Увеличава или намалява звука. За „усили звука“ (+10), „намали звука“ (-10), „по-тихо“.

    Args:
        amount: С колко процента: положително — по-силно, отрицателно — по-тихо.
    """
    endpoint = _endpoint()
    level = endpoint.GetMasterVolumeLevelScalar() * 100 + amount
    endpoint.SetMute(0, None)
    endpoint.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)
    return _volume_now(endpoint)


@jarvis_tool
def mute_sound(mute: bool = True) -> str:
    """Заглушава или пуска обратно звука на компютъра.

    Args:
        mute: true — заглуши, false — върни звука.
    """
    endpoint = _endpoint()
    endpoint.SetMute(1 if mute else 0, None)
    return _volume_now(endpoint)


_MEDIA_KEYS = {"play": 0xB3, "pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}


@jarvis_tool
def media_control(action: str) -> str:
    """Управлява музиката или видеото, което свири (Spotify, YouTube…): пауза, пусни, следваща, предишна.

    Args:
        action: Едно от: play, pause, next, previous, stop.
    """
    key = _MEDIA_KEYS.get(action.lower().strip())
    if key is None:
        raise ValueError("действието трябва да е play, pause, next, previous или stop")
    user32 = ctypes.windll.user32
    user32.keybd_event(key, 0, 1, 0)       # KEYEVENTF_EXTENDEDKEY
    user32.keybd_event(key, 0, 1 | 2, 0)   # + KEYEVENTF_KEYUP
    return {"next": "Следващата.", "previous": "Предишната.", "stop": "Спрях."}.get(action, "Готово.")


# --- Състояние на системата ------------------------------------------------------------------
@jarvis_tool
def system_status() -> str:
    """Умението показва състоянието на системата, включително свободно място на дискове, процесор,
    памет и батерия. Използва се за проверка на ресурсите или при липса на пространство. Примери:
    „Колко свободно място има на диска?/", „Скоро ли ще свърши паметта?/" и „Покажи състоянието на
    компютъра.
    """
    import psutil
    parts = [f"Процесор {psutil.cpu_percent(interval=0.5):.0f}%"]
    memory = psutil.virtual_memory()
    parts.append(f"памет {memory.percent:.0f}% ({memory.used / 2**30:.1f} от {memory.total / 2**30:.0f} GB)")
    for disk in psutil.disk_partitions():
        if "fixed" in disk.opts or disk.fstype:
            try:
                usage = psutil.disk_usage(disk.mountpoint)
            except OSError:
                continue
            parts.append(f"диск {disk.mountpoint[:2]} свободни {usage.free / 2**30:.0f} GB")
    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW,
        ).stdout.strip().split(", ")
        if len(gpu) == 5:
            parts.append(f"видеокарта {gpu[0]}: {gpu[1]}%, {gpu[2]}°C, памет {int(gpu[3]) / 1024:.1f} "
                         f"от {int(gpu[4]) / 1024:.0f} GB")
    except (OSError, subprocess.SubprocessError):
        pass
    battery = psutil.sensors_battery()
    if battery:
        parts.append(f"батерия {battery.percent:.0f}%" + (" (зарежда)" if battery.power_plugged else ""))
    uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    parts.append(f"работи от {uptime.days} дни и {uptime.seconds // 3600} часа" if uptime.days
                 else f"работи от {uptime.seconds // 3600} ч. и {uptime.seconds % 3600 // 60} мин")
    return "; ".join(parts) + "."


# --- Затваряне на програми ---------------------------------------------------------------------
# Процеси, които не бива да се затварят с глас: без тях Windows или самият Митко спира.
_PROTECTED = {"explorer", "svchost", "csrss", "winlogon", "wininit", "services", "lsass", "dwm", "system",
              "smss", "ollama", "ollama app", "python", "pythonw", "msedgewebview2", "taskmgr", "conhost"}
_PROCESS_NAMES = {"calc": "calculatorapp", "mspaint": "mspaint", "winword": "winword"}


def _exe_path(process) -> str | None:
    try:
        return process.exe()
    except Exception:  # noqa: BLE001 — системни процеси не показват пътя си
        return None


def _process_query(name: str) -> str:
    """„хрома“ -> chrome, „калкулатора“ -> calculatorapp, „Steam“ -> steam."""
    command = apps._PROGRAM_KEYS.get(apps.normalize(name))
    if command and not command.endswith(":") and command != "browser":
        base = Path(command).stem.lower()
        return _PROCESS_NAMES.get(base, base)
    found = apps.find_program(name, fuzzy=False)
    if found and found[1].lower().endswith(".exe"):
        return Path(found[1]).stem.lower()
    return apps.to_latin(apps.normalize(name)).replace(" ", "")


@jarvis_tool
def close_program(name: str) -> str:
    """Затваря отворена програма или игра (Chrome, Steam, калкулатора…). Сър потвърждава с бутон.

    Args:
        name: Името на програмата, напр. "Chrome".
    """
    import psutil
    query = _process_query(name)
    matches = [p for p in psutil.process_iter(["name", "pid"])
               if p.info["name"] and query and query in Path(p.info["name"]).stem.lower()]
    names = {Path(p.info["name"]).stem.lower() for p in matches}
    if names & _PROTECTED:
        return f"„{name}“ е част от системата или от мен самия — няма да я затварям, сър."
    if not matches:
        return f"„{name}“ не е отворена в момента."
    images = sorted({p.info["name"] for p in matches}, key=len)  # steam.exe, steamwebhelper.exe…
    exe = images[0]
    if not confirm.ask("Затваряне на програма", f"{', '.join(images)} · {len(matches)} процеса",
                       "Незапазените промени в програмата може да се загубят.", "Затвори"):
        return "Сър отказа — програмата остава отворена."
    # Без /F: програмата получава нормална заявка за затваряне и може да запази работата си.
    for image in images:
        subprocess.run(["taskkill", "/IM", image], capture_output=True, creationflags=NO_WINDOW)
    time.sleep(2)
    still = [p for p in matches if p.is_running()]
    # Приложенията от Microsoft Store (калкулатор, снимки…) не отговарят на обикновена заявка
    # за затваряне, но пазят състоянието си сами — тях затваряме принудително.
    store = {p.info["name"] for p in still if "\\windowsapps\\" in (_exe_path(p) or "").lower()}
    for image in store:
        subprocess.run(["taskkill", "/F", "/IM", image], capture_output=True, creationflags=NO_WINDOW)
    if store:
        time.sleep(1)
        still = [p for p in still if p.is_running()]
    if still:
        return f"Помолих {exe} да се затвори, но още работи — може би пита дали да запази нещо."
    return f"Затворих {exe}."


@jarvis_tool
def power_action(action: str, minutes: int = 0) -> str:
    """Заключва, приспива, изключва или рестартира компютъра, или отменя насрочено изключване.
    Всичко освен заключването иска потвърждение от сър.

    Args:
        action: Едно от: lock, sleep, shutdown, restart, cancel.
        minutes: След колко минути да се изключи/рестартира (0 — след 30 секунди).
    """
    action = action.lower().strip()
    if action == "lock":
        ctypes.windll.user32.LockWorkStation()
        return "Заключих компютъра."
    if action == "cancel":
        done = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=NO_WINDOW).returncode == 0
        return "Отмених изключването." if done else "Няма насрочено изключване."
    titles = {"sleep": "Приспиване на компютъра", "shutdown": "Изключване на компютъра",
              "restart": "Рестартиране на компютъра"}
    if action not in titles:
        raise ValueError("действието трябва да е lock, sleep, shutdown, restart или cancel")
    seconds = max(30, minutes * 60)
    when = "веднага" if action == "sleep" else f"в {(datetime.now() + timedelta(seconds=seconds)):%H:%M}"
    if not confirm.ask(titles[action], f"{titles[action]} — {when}", "Незапазената работа ще се загуби.",
                       {"sleep": "Приспи", "shutdown": "Изключи", "restart": "Рестартирай"}[action]):
        return "Сър отказа — нищо не правя."
    if action == "sleep":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=NO_WINDOW)
        return "Приспивам компютъра."
    flag = "/s" if action == "shutdown" else "/r"
    subprocess.run(["shutdown", flag, "/t", str(seconds)], capture_output=True, creationflags=NO_WINDOW)
    verb = "изключи" if action == "shutdown" else "рестартира"
    return f"Компютърът ще се {verb} {when}. Кажете „отмени изключването“, ако размислите."


# --- Екран и клипборд ------------------------------------------------------------------------
def _pictures_dir() -> Path:
    return folders.known().get("снимки", Path.home() / "Pictures")


@jarvis_tool
def take_screenshot() -> str:
    """Прави снимка на целия екран и я запазва в папка „Снимки\\Митко“."""
    from PIL import ImageGrab
    folder = _pictures_dir() / "Митко"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"екран-{datetime.now():%Y%m%d-%H%M%S}.png"
    ImageGrab.grab(all_screens=True).save(path)
    return f"Запазих снимка на екрана: {path}"


@jarvis_tool
def read_clipboard() -> str:
    """Какво е копирано в момента (клипборда) — за „прочети какво копирах“, „преведи копираното“."""
    import pyperclip
    text = pyperclip.paste() or ""
    if not text.strip():
        return "Клипбордът е празен (или в него има картинка, не текст)."
    return f"Копираният текст ({len(text)} знака):\n{text[:2500]}"


@jarvis_tool
def copy_to_clipboard(text: str) -> str:
    """Копира текст в клипборда, за да го постави сър с Ctrl+V.

    Args:
        text: Текстът за копиране.
    """
    import pyperclip
    pyperclip.copy(text)
    return "Копирах го — поставете с Ctrl+V."


# --- Папки и файлове (общата логика е в jarvis/folders.py) ------------------------------------
@jarvis_tool
def open_folder(name: str) -> str:
    """Отваря папка: Документи, Изтегляния (свалени файлове), Снимки, Музика, Видео, Работен плот или път.

    Args:
        name: Името на папката или пълен път, напр. "изтегляния" или "D:\Игри".
    """
    folder = folders.resolve(name)
    if not folder:
        raise FileNotFoundError(f"не намирам папка „{name}“")
    os.startfile(folder)
    return f"Отворих папка „{folder.name}“."


_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "appdata", "$recycle.bin", ".venv", "venv"}


def list_files(found: list[Path], title: str, limit: int = 8) -> str:
    """Запомня списъка (за „отвори втория“) и го описва."""
    folders.last_found[:] = found[:limit]
    lines = [f"{i}. {f.name} (в {f.parent.name}, {folders.human_size(f.stat().st_size)}, "
             f"{datetime.fromtimestamp(f.stat().st_mtime):%d.%m.%Y})" for i, f in enumerate(folders.last_found, 1)]
    more = f" (първите {limit} от {len(found)})" if len(found) > limit else ""
    return f"{title}{more}: " + "; ".join(lines) + "."


def walk_user_files(deadline_seconds: float = 4):
    """Всички файлове в папките на сър — без системни и програмни подпапки, най-много няколко секунди."""
    deadline = time.monotonic() + deadline_seconds
    for folder in dict.fromkeys(folders.known().values()):
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            for file in files:
                yield Path(root) / file
            if time.monotonic() > deadline:
                return


@jarvis_tool
def find_files(query: str) -> str:
    """Търси файлове по име в Документи, Изтегляния, Работния плот, Снимки, Музика и Видео.

    Args:
        query: Дума от името на файла, напр. "фактура" или "cv".
    """
    words = [w for w in re.split(r"\s+", query.lower().strip()) if w]
    variants = [words, [apps.to_latin(w) for w in words]]
    found = [f for f in walk_user_files() if any(all(w in f.name.lower() for w in v) for v in variants)]
    if not found:
        return f"Не намерих файлове с „{query}“ в името."
    found.sort(key=lambda f: f.stat().st_mtime if f.exists() else 0, reverse=True)
    return list_files(found, "Намерих") + " Мога да отворя някой с open_file."


@jarvis_tool
def open_file(number: int = 1) -> str:
    """Отваря файл от последния списък (търсене, най-големите, последните файлове…).

    Args:
        number: Кой файл от списъка — 1 за първия.
    """
    path = folders.pick(number)
    os.startfile(path)
    return f"Отворих {path.name}."
