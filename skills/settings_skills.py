"""
Настройки на компютъра — само с разрешение на сър.

Яркост, Bluetooth, Wi-Fi, тъмен режим, прозрачност, режим на захранване, изключване на екрана
и заспиване, скорост на мишката, тапет, звуков изход, разширения и скрити файлове.

Всяка промяна показва прозорче „стара стойност → нова“ и чака бутона „Промени“
(jarvis/confirm.py). Старата стойност се пази: „върни настройката“ я възстановява.
Само четенето (какви са настройките) не иска разрешение.
"""
import base64
import ctypes
import os
import re
import subprocess
import winreg
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from jarvis import confirm, folders, jarvis_tool

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
user32 = ctypes.windll.user32

# Последните промени — (какво, как се връща). „Върни настройката“ взима последната.
_undo: list[tuple[str, Callable[[], None]]] = []


def _change(setting: str, old: str, new: str, apply: Callable[[], None], undo: Callable[[], None],
            note: str = "") -> str:
    """Пита сър с бутон и чак тогава променя. Запомня как да се върне."""
    if old == new:
        return f"{setting}: вече е {new}."
    if not confirm.ask("Промяна на настройка", f"{setting}: {old} → {new}",
                       note or "Ако не Ви хареса, кажете „върни настройката“.", "Промени"):
        return "Сър отказа — нищо не променям."
    apply()
    _undo.append((f"{setting}: {new} → {old}", undo))
    del _undo[:-20]
    return f"Готово. {setting}: {new} (беше {old})."


def _powershell(script: str, **env: str) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40,
        creationflags=NO_WINDOW, env={**os.environ, **env},
    ).stdout.strip()


def _on_off(on: bool) -> str:
    return "включен" if on else "изключен"


# --- Яркост ------------------------------------------------------------------------------------
class _PhysicalMonitor(ctypes.Structure):
    _fields_ = [("handle", wintypes.HANDLE), ("description", wintypes.WCHAR * 128)]


def _dxva2():
    dxva2 = ctypes.windll.dxva2
    dword_p = ctypes.POINTER(wintypes.DWORD)
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, dword_p]
    dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD,
                                                      ctypes.POINTER(_PhysicalMonitor)]
    dxva2.GetMonitorBrightness.argtypes = [wintypes.HANDLE, dword_p, dword_p, dword_p]
    dxva2.SetMonitorBrightness.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    dxva2.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, ctypes.POINTER(_PhysicalMonitor)]
    return dxva2


def _ddc_brightness(level: int | None = None) -> list[int]:
    """Яркостта на мониторите (0–100) през DDC/CI (външни монитори); с `level` — и я сменя."""
    dxva2 = _dxva2()
    found: list[_PhysicalMonitor] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                        wintypes.LPARAM)
    def collect(hmonitor, _hdc, _rect, _data):
        count = wintypes.DWORD()
        if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)) and count.value:
            monitors = (_PhysicalMonitor * count.value)()
            if dxva2.GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, monitors):
                found.extend(monitors)
        return True

    user32.EnumDisplayMonitors(None, None, collect, 0)
    values = []
    try:
        for monitor in found:
            low, now, high = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
            if not dxva2.GetMonitorBrightness(monitor.handle, ctypes.byref(low), ctypes.byref(now),
                                              ctypes.byref(high)):
                continue  # мониторът не поддържа DDC/CI
            span = max(1, high.value - low.value)
            if level is None:
                values.append(round((now.value - low.value) * 100 / span))
            elif dxva2.SetMonitorBrightness(monitor.handle, low.value + round(span * level / 100)):
                values.append(level)
    finally:
        if found:
            dxva2.DestroyPhysicalMonitors(len(found), (_PhysicalMonitor * len(found))(*found))
    return values


def _panel_brightness(level: int | None = None) -> int | None:
    """Вграденият екран на лаптоп (през WMI)."""
    if level is None:
        out = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
                          "-ErrorAction SilentlyContinue | Select-Object -First 1).CurrentBrightness")
        return int(out) if out.isdigit() else None
    _powershell("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={level}}}")
    return level


def _brightness() -> int | None:
    values = _ddc_brightness()
    return round(sum(values) / len(values)) if values else _panel_brightness()


def _set_brightness_everywhere(level: int) -> None:
    if not _ddc_brightness(level):
        _panel_brightness(level)


def _brightness_to(level: int) -> str:
    now = _brightness()
    if now is None:
        return ("Не мога да сменя яркостта: мониторът не приема команди (DDC/CI е изключено в менюто "
                "му) — сменете я от бутоните на монитора.")
    level = max(0, min(100, level))
    return _change("Яркостта на екрана", f"{now}%", f"{level}%",
                   lambda: _set_brightness_everywhere(level), lambda: _set_brightness_everywhere(now))


@jarvis_tool
def set_brightness(level: int) -> str:
    """Яркостта на екрана (монитора) на точна стойност — „яркостта на 50“. Сър потвърждава с бутон.

    Args:
        level: От 0 до 100.
    """
    return _brightness_to(level)


@jarvis_tool
def change_brightness(amount: int) -> str:
    """По-ярко или по-тъмно: „увеличи яркостта“ (+20), „намали яркостта“, „по-тъмно“ (-20).
    Сър потвърждава с бутон.

    Args:
        amount: С колко процента: положително — по-ярко, отрицателно — по-тъмно.
    """
    now = _brightness()
    return _brightness_to((now if now is not None else 50) + amount)


# --- Bluetooth и Wi-Fi --------------------------------------------------------------------------
_RADIOS = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
  $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) `
  ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
foreach ($r in $radios) {
  if ($env:RADIO_KIND -and "$($r.Kind)" -eq $env:RADIO_KIND) {
    $status = Await ($r.SetStateAsync($env:RADIO_STATE)) ([Windows.Devices.Radios.RadioAccessStatus])
    "SET|$($r.Kind)|$status"
  }
  "$($r.Kind)|$($r.State)"
}
"""
_RADIO_NAMES = {"Bluetooth": "Bluetooth", "WiFi": "Wi-Fi"}


def _radios(kind: str = "", state: str = "") -> dict[str, str]:
    """{"Bluetooth": "On", "WiFi": "Off", "SET": "Allowed"} — радиата на компютъра (и промяна)."""
    found = {}
    for line in _powershell(_RADIOS, RADIO_KIND=kind, RADIO_STATE=state).splitlines():
        parts = line.strip().split("|")
        if parts[0] == "SET" and len(parts) == 3:
            found["SET"] = parts[2]
        elif len(parts) == 2:
            found.setdefault(parts[0], parts[1])
    return found


def _set_radio(kind: str, on: bool) -> str:
    name = _RADIO_NAMES[kind]
    radios = _radios()
    if kind not in radios:
        return f"На този компютър няма {name} — няма какво да включа или изключа."
    old = radios[kind] == "On"

    def apply(value: bool) -> None:
        status = _radios(kind, "On" if value else "Off").get("SET")
        if status != "Allowed":
            raise PermissionError(f"Windows не позволи промяната ({status}) — вижте Настройки → Поверителност → Радиа")

    return _change(name, _on_off(old), _on_off(on), lambda: apply(on), lambda: apply(old))


@jarvis_tool
def set_bluetooth(on: bool = True) -> str:
    """Включва или изключва Bluetooth. Сър потвърждава с бутон.

    Args:
        on: true — включи, false — изключи.
    """
    return _set_radio("Bluetooth", on)


@jarvis_tool
def set_wifi(on: bool = True) -> str:
    """Включва или изключва Wi-Fi (безжичния интернет). Сър потвърждава с бутон.

    Args:
        on: true — включи, false — изключи.
    """
    return _set_radio("WiFi", on)


# --- Тема ---------------------------------------------------------------------------------------
_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def _get_dword(path: str, name: str, default: int) -> int:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return int(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return default


def _set_dwords(path: str, values: dict[str, int], broadcast: str = "") -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
    if broadcast:  # WM_SETTINGCHANGE — програмите сменят вида си веднага
        user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, broadcast, 0x2, 1000, None)


def _theme(dark: bool) -> None:
    _set_dwords(_PERSONALIZE, {"AppsUseLightTheme": 0 if dark else 1, "SystemUsesLightTheme": 0 if dark else 1},
                "ImmersiveColorSet")


@jarvis_tool
def toggle_dark_mode(dark: bool = True) -> str:
    """Тъмен или светъл режим на Windows. Сър потвърждава с бутон.

    Args:
        dark: true — тъмен, false — светъл.
    """
    is_dark = _get_dword(_PERSONALIZE, "AppsUseLightTheme", 1) == 0
    label = lambda value: "тъмна" if value else "светла"  # noqa: E731
    return _change("Темата на Windows", label(is_dark), label(dark), lambda: _theme(dark), lambda: _theme(is_dark))


@jarvis_tool
def set_transparency(on: bool = True) -> str:
    """Прозрачните ефекти на Windows (лентата на задачите, менюто Start). Сър потвърждава с бутон.

    Args:
        on: true — включи, false — изключи.
    """
    was_on = _get_dword(_PERSONALIZE, "EnableTransparency", 1) == 1
    apply = lambda value: _set_dwords(_PERSONALIZE, {"EnableTransparency": int(value)}, "ImmersiveColorSet")  # noqa: E731
    label = lambda value: "включена" if value else "изключена"  # noqa: E731
    return _change("Прозрачността", label(was_on), label(on), lambda: apply(on), lambda: apply(was_on))


# --- Захранване ---------------------------------------------------------------------------------
_PLAN_LABELS = {
    "381b4222-f694-41f0-9685-ff5bb260df2e": "балансиран",
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "висока производителност",
    "a1841308-3541-4fab-bc81-f71556f20b4a": "пестене на енергия",
    "e9a42b02-d5df-448d-aa00-03f14749eb61": "максимална производителност",
}
_PLAN_WORDS = [
    (re.compile(r"максимал|ultimate|най-висок|най-мощ", re.IGNORECASE), "e9a42b02-d5df-448d-aa00-03f14749eb61"),
    (re.compile(r"висок|производит|бърз|мощ|игр|гейм|game|performance", re.IGNORECASE),
     "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"),
    (re.compile(r"пест|иконом|тих|батери|saver", re.IGNORECASE), "a1841308-3541-4fab-bc81-f71556f20b4a"),
    (re.compile(r"баланс|нормал|обикнов|стандарт|balanced", re.IGNORECASE), "381b4222-f694-41f0-9685-ff5bb260df2e"),
]


def _powercfg(*args: str) -> str:
    return subprocess.run(["powercfg", *args], capture_output=True, text=True, encoding="oem", errors="replace",
                          timeout=20, creationflags=NO_WINDOW).stdout


def _plans() -> list[tuple[str, str, bool]]:
    """[(GUID, име, активен ли е)] — плановете за захранване на компютъра."""
    plans: dict[str, tuple[str, bool]] = {}
    for match in re.finditer(r"([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})\s+\((.+?)\)(\s*\*)?", _powercfg("/list")):
        guid, name, active = match.group(1), match.group(2), bool(match.group(3))
        label = _PLAN_LABELS.get(guid, name)
        plans[guid] = (label, active or plans.get(guid, ("", False))[1])
    return [(guid, label, active) for guid, (label, active) in plans.items()]


@jarvis_tool
def set_power_plan(plan: str) -> str:
    """Режимът на захранване: „балансиран“, „висока производителност“ (за игри), „пестене на енергия“,
    „максимална производителност“ или името на друг план на компютъра. Сър потвърждава с бутон.

    Args:
        plan: Кой режим, с думи.
    """
    plans = _plans()
    current = next(((g, label) for g, label, active in plans if active), ("", "неизвестен"))
    wanted = next((guid for pattern, guid in _PLAN_WORDS if pattern.search(plan)), None)
    target = next(((g, label) for g, label, _ in plans if g == wanted), None) or \
        next(((g, label) for g, label, _ in plans if plan.lower().strip() in label.lower()), None)
    if not target:
        return f"Няма такъв режим. Режимите на този компютър: {', '.join(label for _, label, _ in plans)}."
    old_guid = current[0]
    return _change("Режимът на захранване", current[1], target[1],
                   lambda: _powercfg("/setactive", target[0]), lambda: _powercfg("/setactive", old_guid))


def _idle_minutes(subgroup: str, setting: str) -> int | None:
    """След колко минути без работа (при захранване от мрежата). 0 — никога."""
    values = re.findall(r"0x([0-9a-f]{8})", _powercfg("/q", "SCHEME_CURRENT", subgroup, setting))
    return int(values[-2], 16) // 60 if len(values) >= 2 else None


def _minutes(value: int | None) -> str:
    if value is None:
        return "неизвестно"
    return "никога" if value == 0 else f"след {value} мин"


def _set_idle(kind: str, minutes: int) -> None:
    for power in ("ac", "dc"):
        _powercfg("/change", f"{kind}-timeout-{power}", str(minutes))


@jarvis_tool
def set_screen_timeout(minutes: int) -> str:
    """След колко минути без работа да се изключва екранът (0 — никога). Сър потвърждава с бутон.

    Args:
        minutes: Минути; 0 — екранът да не се изключва.
    """
    old = _idle_minutes("SUB_VIDEO", "VIDEOIDLE")
    minutes = max(0, minutes)
    return _change("Изключването на екрана", _minutes(old), _minutes(minutes),
                   lambda: _set_idle("monitor", minutes), lambda: _set_idle("monitor", old or 0))


@jarvis_tool
def set_sleep_timeout(minutes: int) -> str:
    """След колко минути без работа компютърът да заспива (0 — никога). Сър потвърждава с бутон.

    Args:
        minutes: Минути; 0 — да не заспива.
    """
    old = _idle_minutes("SUB_SLEEP", "STANDBYIDLE")
    minutes = max(0, minutes)
    return _change("Заспиването на компютъра", _minutes(old), _minutes(minutes),
                   lambda: _set_idle("standby", minutes), lambda: _set_idle("standby", old or 0))


# --- Мишка и тапет ------------------------------------------------------------------------------
def _mouse_speed() -> int:
    speed = ctypes.c_int()
    user32.SystemParametersInfoW(0x0070, 0, ctypes.byref(speed), 0)  # SPI_GETMOUSESPEED
    return speed.value


def _apply_mouse_speed(speed: int) -> None:
    user32.SystemParametersInfoW(0x0071, 0, ctypes.c_void_p(speed), 0x01 | 0x02)  # SPI_SETMOUSESPEED, запази


@jarvis_tool
def set_mouse_speed(speed: int) -> str:
    """Скоростта на показалеца на мишката: от 1 (най-бавно) до 20 (най-бързо); в Windows обичайно е 10.
    Сър потвърждава с бутон.

    Args:
        speed: От 1 до 20.
    """
    old, speed = _mouse_speed(), max(1, min(20, speed))
    return _change("Скоростта на мишката", f"{old} от 20", f"{speed} от 20",
                   lambda: _apply_mouse_speed(speed), lambda: _apply_mouse_speed(old))


def _wallpaper() -> str:
    buffer = ctypes.create_unicode_buffer(520)
    user32.SystemParametersInfoW(0x0073, 520, buffer, 0)  # SPI_GETDESKWALLPAPER
    return buffer.value


def _apply_wallpaper(path: str) -> None:
    if not user32.SystemParametersInfoW(0x0014, 0, path, 0x01 | 0x02):  # SPI_SETDESKWALLPAPER
        raise OSError("Windows не прие снимката за тапет")


@jarvis_tool
def set_wallpaper(number: int = 1, path: str = "") -> str:
    """Слага снимка за фон (тапет) на работния плот: файл от последния списък (след търсене на файлове)
    или пълен път. Сър потвърждава с бутон.

    Args:
        number: Кой файл от последния списък — 1 за първия.
        path: Пълен път до снимката (по желание).
    """
    image = Path(path.strip().strip('"')) if path.strip() else folders.pick(number)
    if not image.exists():
        raise FileNotFoundError(f"няма файл „{image}“")
    if image.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".jfif"):
        raise ValueError(f"„{image.name}“ не е снимка")
    old = _wallpaper()
    return _change("Тапетът", Path(old).name or "без снимка", image.name,
                   lambda: _apply_wallpaper(str(image)), lambda: _apply_wallpaper(old))


# --- Звуков изход -------------------------------------------------------------------------------
_OUTPUT_WORDS = [
    (re.compile(r"слушалк|хедсет|headphone|headset", re.IGNORECASE),
     re.compile(r"headphone|headset|слушалк|kraken|buds|airpods|arctis|hyperx|razer", re.IGNORECASE)),
    (re.compile(r"колон|тонколон|високоговор|говорител|speaker", re.IGNORECASE),
     re.compile(r"speaker|говорител|колон|realtek|high definition audio device", re.IGNORECASE)),
    (re.compile(r"монитор|екран|телевизор|\bтв\b|hdmi|display", re.IGNORECASE),
     re.compile(r"nvidia|amd high definition|hdmi|displayport|monitor|монитор|tv|display", re.IGNORECASE)),
]


def _outputs() -> tuple[list[tuple[str, str]], str]:
    """([(име, id)] на включените звукови изходи, id на избрания в момента)."""
    import comtypes
    from pycaw.pycaw import AudioUtilities
    comtypes.CoInitialize()
    devices = [(d.FriendlyName, d.id) for d in AudioUtilities.GetAllDevices()
               if str(d.state).endswith("Active") and d.id.startswith("{0.0.0.")]  # само изходи
    return devices, AudioUtilities.GetSpeakers().id


def _apply_output(device_id: str) -> None:
    import comtypes
    from pycaw.constants import ERole
    from pycaw.pycaw import AudioUtilities
    comtypes.CoInitialize()
    AudioUtilities.SetDefaultDevice(device_id, roles=[ERole.eConsole, ERole.eMultimedia, ERole.eCommunications])


@jarvis_tool
def audio_outputs() -> str:
    """Кои звукови изходи има (колони, слушалки, монитор) и през кой е звукът в момента."""
    devices, current = _outputs()
    if not devices:
        return "Не намирам включени звукови изходи."
    return "Звукови изходи: " + "; ".join(f"{name}{' (избран)' if d == current else ''}" for name, d in devices) + "."


@jarvis_tool
def set_audio_output(name: str = "") -> str:
    """Пуска звука през друго устройство: слушалките, колоните, монитора… Празно — през следващото.
    Сър потвърждава с бутон.

    Args:
        name: Дума от името или вида: "слушалки", "колони", "монитор", "Razer"… (празно — следващото).
    """
    devices, current = _outputs()
    if len(devices) < 2:
        return f"Има само един звуков изход ({devices[0][0] if devices else 'няма'}) — няма към какво да превключа."
    wanted = name.lower().strip()
    target = None
    if not wanted or re.search(r"следващ|друг|смени", wanted):
        index = next((i for i, (_, d) in enumerate(devices) if d == current), -1)
        target = devices[(index + 1) % len(devices)]
    else:
        target = next((dev for dev in devices if wanted in dev[0].lower()), None)
        for kind, names in _OUTPUT_WORDS:
            if not target and kind.search(wanted):
                target = next((dev for dev in devices if names.search(dev[0])), None)
    if not target:
        return f"Не намирам изход „{name}“. Има: {', '.join(n for n, _ in devices)}."
    old_name = next((n for n, d in devices if d == current), "неизвестен")
    return _change("Звуковият изход", old_name, target[0],
                   lambda: _apply_output(target[1]), lambda: _apply_output(current))


# --- Файлове в Explorer -------------------------------------------------------------------------
_ADVANCED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


def _refresh_explorer() -> None:
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED


@jarvis_tool
def show_file_extensions(show: bool = True) -> str:
    """Показва или скрива разширенията на файловете (.docx, .exe…) в Explorer. Сър потвърждава с бутон.

    Args:
        show: true — показвай, false — скривай.
    """
    shown = _get_dword(_ADVANCED, "HideFileExt", 1) == 0

    def apply(value: bool) -> None:
        _set_dwords(_ADVANCED, {"HideFileExt": 0 if value else 1})
        _refresh_explorer()

    label = lambda value: "показват се" if value else "скрити"  # noqa: E731
    return _change("Разширенията на файловете", label(shown), label(show), lambda: apply(show), lambda: apply(shown))


@jarvis_tool
def show_hidden_files(show: bool = True) -> str:
    """Показва или скрива скритите файлове и папки в Explorer. Сър потвърждава с бутон.

    Args:
        show: true — показвай, false — скривай.
    """
    shown = _get_dword(_ADVANCED, "Hidden", 2) == 1

    def apply(value: bool) -> None:
        _set_dwords(_ADVANCED, {"Hidden": 1 if value else 2})
        _refresh_explorer()

    label = lambda value: "показват се" if value else "скрити"  # noqa: E731
    return _change("Скритите файлове", label(shown), label(show), lambda: apply(show), lambda: apply(shown))


# --- Връщане и преглед ----------------------------------------------------------------------------
@jarvis_tool
def undo_setting_change() -> str:
    """Връща последната настройка, която си променил (яркост, режим, тапет, звуков изход…), както
    беше. За „върни настройката“, „върни както беше“. Сър потвърждава с бутон."""
    if not _undo:
        return "Не съм променял настройки, откакто съм включен — нямам какво да върна."
    what, undo = _undo[-1]
    if not confirm.ask("Връщане на настройка", what, "Връщам предишната стойност.", "Върни"):
        return "Сър отказа — оставям настройката както е."
    _undo.pop()
    undo()
    return f"Върнах: {what}."


def _safe(read: Callable[[], str]) -> str | None:
    try:
        return read()
    except Exception:  # noqa: BLE001 — показва се само това, което може да се прочете
        return None


@jarvis_tool
def device_settings() -> str:
    """Текущите настройки на компютъра: яркост, тема, захранване, изключване на екрана и заспиване,
    мишка, звуков изход, Bluetooth, Wi-Fi, разширения и скрити файлове. Само чете — не променя нищо."""
    def brightness() -> str:
        value = _brightness()
        return f"яркост {value}%" if value is not None else "яркост — не се управлява от Windows"

    def radios() -> str:
        found = _radios()
        parts = [f"{_RADIO_NAMES[k]} {_on_off(found[k] == 'On')}" for k in _RADIO_NAMES if k in found]
        return ", ".join(parts) or "няма Bluetooth и Wi-Fi"

    def output() -> str:
        devices, current = _outputs()
        return "звукът през " + next((n for n, d in devices if d == current), "неизвестен изход")

    parts = [
        _safe(brightness),
        _safe(lambda: "тема " + ("тъмна" if _get_dword(_PERSONALIZE, "AppsUseLightTheme", 1) == 0 else "светла")),
        _safe(lambda: "захранване: " + next(label for _, label, active in _plans() if active)),
        _safe(lambda: "екранът се изключва " + _minutes(_idle_minutes("SUB_VIDEO", "VIDEOIDLE"))),
        _safe(lambda: "заспива " + _minutes(_idle_minutes("SUB_SLEEP", "STANDBYIDLE"))),
        _safe(lambda: f"мишка {_mouse_speed()} от 20"),
        _safe(output),
        _safe(radios),
        _safe(lambda: "разширенията " + ("се показват" if _get_dword(_ADVANCED, "HideFileExt", 1) == 0 else "са скрити")),
    ]
    return "Настройки: " + "; ".join(p for p in parts if p) + "."
