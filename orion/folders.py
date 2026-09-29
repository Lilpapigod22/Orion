"""
Папките на сър (Документи, Изтегляния, Работен плот…) и последният списък с файлове,
за да работи „отвори втория“, „изтрий първия“ след търсене.
"""
import os
from pathlib import Path

# Последно показаните файлове (от търсене, „най-големите“, „последните“…).
last_found: list[Path] = []

ALIASES = {
    "документи": "документи", "documents": "документи", "снимки": "снимки", "картини": "снимки",
    "pictures": "снимки", "музика": "музика", "music": "музика", "видео": "видео", "видеа": "видео",
    "клипове": "видео", "videos": "видео", "работен плот": "работен плот", "десктоп": "работен плот",
    "desktop": "работен плот", "изтегляния": "изтегляния", "свалени": "изтегляния",
    "свалените": "изтегляния", "даунлоуд": "изтегляния", "downloads": "изтегляния",
}


def known() -> dict[str, Path]:
    """Истинските папки на Windows (може да са преместени в OneDrive или на друг диск)."""
    folders = {}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            for name, value_name in [("документи", "Personal"), ("снимки", "My Pictures"), ("музика", "My Music"),
                                     ("видео", "My Video"), ("работен плот", "Desktop"),
                                     ("изтегляния", "{374DE290-123F-4565-9164-39C4925E467B}")]:
                try:
                    folders[name] = Path(os.path.expandvars(winreg.QueryValueEx(key, value_name)[0]))
                except OSError:
                    pass
    except OSError:
        pass
    home = Path.home()
    for name, sub in [("документи", "Documents"), ("снимки", "Pictures"), ("музика", "Music"),
                      ("видео", "Videos"), ("работен плот", "Desktop"), ("изтегляния", "Downloads")]:
        folders.setdefault(name, home / sub)
    return folders


def resolve(name: str) -> Path | None:
    """„изтегляния“, „работния плот“ или пълен път -> папка."""
    from .apps import normalize
    raw = name.strip().strip('"')
    if raw and os.path.isdir(raw):
        return Path(raw)
    key = next((v for k, v in ALIASES.items() if normalize(k) in normalize(raw)), None) if raw else None
    folder = known().get(key) if key else None
    return folder if folder and folder.is_dir() else None


def pick(number: int) -> Path:
    """Файл номер `number` от последния списък."""
    if not last_found:
        raise LookupError("първо потърсете файловете — нямам списък")
    if not 1 <= number <= len(last_found):
        raise LookupError(f"в списъка има {len(last_found)} файла")
    path = last_found[number - 1]
    if not path.exists():
        raise FileNotFoundError(f"{path.name} вече го няма")
    return path


def human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
