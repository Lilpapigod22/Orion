"""
Windows: отворени програми и прозорци, какво натоварва компютъра, превключване към прозорец,
„покажи работния плот“, страниците на Настройки, инсталирани програми, писане на текст
в друга програма и версията на Windows. (Промяната на настройки — тъмен режим, яркост… —
е в settings_skills.py и става само с разрешение на сър.)
"""
import ctypes
import os
import platform
import sys
import time
from ctypes import wintypes

from jarvis import jarvis_tool, vision

user32 = ctypes.windll.user32


def _windows() -> list[tuple[int, str, str]]:
    """Видимите прозорци: (hwnd, заглавие, програма)."""
    import psutil
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                program = psutil.Process(pid.value).name().removesuffix(".exe")
            except psutil.Error:
                program = "?"
            if buffer.value not in ("Program Manager", "Settings", "Windows Input Experience"):
                found.append((hwnd, buffer.value, program))
        return True

    user32.EnumWindows(collect, 0)
    return found


@jarvis_tool
def list_open_windows() -> str:
    """Кои прозорци и програми са отворени в момента."""
    windows = _windows()
    if not windows:
        return "Няма отворени прозорци."
    return f"Отворени прозорци ({len(windows)}): " + "; ".join(f"{t[:60]} ({p})" for _, t, p in windows[:20]) + "."


@jarvis_tool
def focus_window(title: str) -> str:
    """Превключва към отворен прозорец (извежда го отпред). За „покажи ми Chrome“, „върни се в Word“.

    Args:
        title: Дума от заглавието или името на програмата.
    """
    wanted = title.lower().strip()
    match = next(((h, t) for h, t, p in _windows() if wanted in t.lower() or wanted in p.lower()), None)
    if not match:
        return f"Не намирам отворен прозорец „{title}“."
    hwnd, name = match
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.keybd_event(0x12, 0, 0, 0)  # Alt — Windows позволява смяна на фокуса само след натискане
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    return f"Показах „{name[:60]}“."


@jarvis_tool
def minimize_all_windows() -> str:
    """Скрива всички прозорци и показва работния плот (като Win+D)."""
    user32.keybd_event(0x5B, 0, 0, 0)  # Win
    user32.keybd_event(0x44, 0, 0, 0)  # D
    user32.keybd_event(0x44, 0, 2, 0)
    user32.keybd_event(0x5B, 0, 2, 0)
    return "Показах работния плот."


@jarvis_tool
def resource_hogs() -> str:
    """Умението resource_hogs идентифицира програми, които натоварват процесора и паметта, причинявайки
    забавяне на компютъра. Използва се при въпроси като „Защо компютърът ми е толкова бавен?","Кои
    приложения консумират много ресурси?" или „Какво изтощава системата?".
    """
    import psutil
    processes = list(psutil.process_iter(["name", "memory_info"]))
    for p in processes:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(1)
    usage = []
    for p in processes:
        try:
            usage.append((p.cpu_percent(None) / psutil.cpu_count(), p.info["memory_info"].rss, p.info["name"]))
        except (psutil.Error, AttributeError):
            continue
    cpu = sorted((u for u in usage if u[2] != "System Idle Process"), reverse=True)[:5]
    memory: dict[str, int] = {}
    for _, rss, name in usage:
        memory[name] = memory.get(name, 0) + rss
    top_memory = sorted(memory.items(), key=lambda i: i[1], reverse=True)[:5]
    return ("Процесор: " + ", ".join(f"{n} {c:.0f}%" for c, _, n in cpu) + ". Памет: "
            + ", ".join(f"{n} {m / 2**30:.1f} GB" for n, m in top_memory) + ".")


@jarvis_tool
def running_programs() -> str:
    """Кои програми работят (с прозорец) — без системните процеси."""
    programs = sorted({p for _, _, p in _windows()})
    return f"Работят {len(programs)} програми: {', '.join(programs)}." if programs else "Няма отворени програми."


_SETTINGS = {
    "wi-fi": "network-wifi", "wifi": "network-wifi", "уай фай": "network-wifi", "мрежа": "network-status",
    "bluetooth": "bluetooth", "блутут": "bluetooth", "звук": "sound", "дисплей": "display", "екран": "display",
    "резолюция": "display", "обновления": "windowsupdate", "ъпдейт": "windowsupdate", "update": "windowsupdate",
    "приложения": "appsfeatures", "програми": "appsfeatures", "мишка": "mousetouchpad", "клавиатура": "typing",
    "език": "regionlanguage", "поверителност": "privacy", "фон": "personalization-background",
    "тапет": "personalization-background", "теми": "themes", "цветове": "personalization-colors",
    "захранване": "powersleep", "батерия": "batterysaver", "съхранение": "storagesense", "диск": "storagesense",
    "принтер": "printers", "дата": "dateandtime", "час": "dateandtime", "известия": "notifications",
    "игри": "gaming-gamebar", "акаунт": "yourinfo", "по подразбиране": "defaultapps", "браузър": "defaultapps",
    "стартиране": "startupapps", "микрофон": "privacy-microphone", "камера": "privacy-webcam",
}


@jarvis_tool
def open_settings_page(page: str) -> str:
    """Отваря страница от Настройките на Windows: Wi-Fi, Bluetooth, звук, дисплей, обновления,
    приложения, фон, захранване, съхранение, принтери, микрофон, програми при стартиране…

    Args:
        page: Коя страница, напр. "bluetooth" или "звук".
    """
    key = next((v for k, v in _SETTINGS.items() if k in page.lower()), None)
    os.startfile(f"ms-settings:{key or ''}")
    return f"Отворих настройките{' — ' + page if key else ''}."


@jarvis_tool
def installed_programs(search: str = "") -> str:
    """Кои програми са инсталирани — или дали е инсталирана определена.

    Args:
        search: Дума от името (празно — колко са общо и някои от тях).
    """
    import winreg
    names = set()
    for root, path in [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                       (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")]:
        try:
            with winreg.OpenKey(root, path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                            name = winreg.QueryValueEx(sub, "DisplayName")[0]
                            hidden = _has(sub, "SystemComponent") and winreg.QueryValueEx(sub, "SystemComponent")[0] == 1
                            if name and not hidden:  # без системните компоненти и обновленията
                                names.add(name.strip())
                    except OSError:
                        continue
        except OSError:
            continue
    if search.strip():
        found = sorted(n for n in names if search.lower() in n.lower())
        return (f"Да, инсталирано: {', '.join(found[:10])}." if found else f"„{search}“ не е инсталирана.")
    return f"Инсталирани са {len(names)} програми, напр.: {', '.join(sorted(names)[:25])}…"


def _has(key, value_name: str) -> bool:
    import winreg
    try:
        winreg.QueryValueEx(key, value_name)
        return True
    except OSError:
        return False


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def send_text(text: str) -> None:
    """Изписва текста в активния прозорец, буква по буква (и кирилица, и емоджита)."""
    events = []
    for ch in text:
        if ch == "\n":
            events += [_INPUT(1, _INPUTUNION(ki=_KEYBDINPUT(0x0D, 0, 0, 0, 0))),
                       _INPUT(1, _INPUTUNION(ki=_KEYBDINPUT(0x0D, 0, 2, 0, 0)))]
            continue
        units = ch.encode("utf-16-le")
        for i in range(0, len(units), 2):  # символите извън BMP са две „половинки“
            code = int.from_bytes(units[i:i + 2], "little")
            events += [_INPUT(1, _INPUTUNION(ki=_KEYBDINPUT(0, code, 4, 0, 0))),        # KEYEVENTF_UNICODE
                       _INPUT(1, _INPUTUNION(ki=_KEYBDINPUT(0, code, 4 | 2, 0, 0)))]
    array = (_INPUT * len(events))(*events)
    user32.SendInput(len(events), array, ctypes.sizeof(_INPUT))


@jarvis_tool
def type_text(text: str) -> str:
    """Написва текст в програмата, в която сър пише в момента (Word, бележник, чат…) — като диктовка.

    Args:
        text: Текстът за писане.
    """
    vision.minimize_window()  # Митко се прибира, фокусът се връща в програмата на сър
    time.sleep(0.6)
    send_text(text)
    return f"Написах {len(text)} знака (прибрах се долу, за да не преча)."


@jarvis_tool
def windows_version() -> str:
    """Коя версия на Windows е инсталирана."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
        product = winreg.QueryValueEx(key, "ProductName")[0]
        display = winreg.QueryValueEx(key, "DisplayVersion")[0] if _has(key, "DisplayVersion") else ""
    build = sys.getwindowsversion().build
    if build >= 22000:
        product = product.replace("Windows 10", "Windows 11")
    return f"{product} {display} (build {build}, {platform.machine()})."
