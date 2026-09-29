"""
Файлове: нова папка, последни и най-големи файлове, размер на папка, преименуване, копиране,
преместване, изтриване (в Кошчето), архиви, четене на документи, почистване на временните
файлове и Кошчето. Изтриването и почистването стават само след бутон от сър.
"""
import ctypes
import os
import re
import shutil
import tempfile
import time
import zipfile
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from jarvis import confirm, folders, jarvis_tool

_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "appdata", "$recycle.bin", ".venv", "venv"}


def _walk(roots, seconds: float = 5):
    deadline = time.monotonic() + seconds
    for root_folder in roots:
        for root, dirs, files in os.walk(root_folder):
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            for file in files:
                yield Path(root) / file
            if time.monotonic() > deadline:
                return


def _describe(found: list[Path], title: str, limit: int = 8) -> str:
    folders.last_found[:] = found[:limit]
    rows = []
    for i, f in enumerate(folders.last_found, 1):
        try:
            rows.append(f"{i}. {f.name} ({folders.human_size(f.stat().st_size)}, в {f.parent.name}, "
                        f"{datetime.fromtimestamp(f.stat().st_mtime):%d.%m.%Y})")
        except OSError:
            continue
    return f"{title}: " + "; ".join(rows) + ". (Мога да отворя, преименувам, преместя или изтрия някой по номер.)"


def _target_folder(name: str) -> Path:
    folder = folders.resolve(name)
    if not folder:
        raise FileNotFoundError(f"не намирам папка „{name}“")
    return folder


@jarvis_tool
def create_folder(name: str, location: str = "работен плот") -> str:
    """Създава нова папка.

    Args:
        name: Името на новата папка.
        location: Къде — "работен плот", "документи", "изтегляния" или пълен път.
    """
    path = _target_folder(location) / re.sub(r'[<>:"/\\|?*]', "", name).strip()
    path.mkdir(parents=True, exist_ok=True)
    return f"Създадох папка „{path.name}“ в {path.parent.name}."


@jarvis_tool
def recent_files(days: int = 3) -> str:
    """Файловете, променяни последно (в Документи, Изтегляния, Работен плот…).

    Args:
        days: За колко дни назад (по подразбиране 3).
    """
    since = time.time() - max(1, days) * 86400
    found = [f for f in _walk(folders.known().values()) if f.stat().st_mtime >= since]
    found.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return _describe(found, f"Последни файлове (за {days} дни)") if found else f"Няма файлове, променяни в последните {days} дни."


@jarvis_tool
def largest_files(location: str = "") -> str:
    """Най-големите файлове — за да се освободи място на диска.

    Args:
        location: Папка ("изтегляния", "документи" или път). Празно — всичките папки на сър.
    """
    roots = [_target_folder(location)] if location.strip() else list(dict.fromkeys(folders.known().values()))
    found = sorted(_walk(roots, seconds=8), key=lambda f: f.stat().st_size if f.exists() else 0, reverse=True)
    return _describe(found, "Най-големите файлове") if found else "Не намерих файлове."


@jarvis_tool
def folder_size(location: str) -> str:
    """Колко място заема папка и колко файла има в нея.

    Args:
        location: Папката — "изтегляния", "документи" или пълен път.
    """
    folder = _target_folder(location)
    total = count = 0
    for f in _walk([folder], seconds=10):
        try:
            total += f.stat().st_size
            count += 1
        except OSError:
            pass
    return f"Папка „{folder.name}“: {folders.human_size(total)} в {count} файла."


@jarvis_tool
def latest_download() -> str:
    """Последно изтегленият файл (в Изтегляния) — за „отвори последното, което свалих“."""
    downloads = folders.known().get("изтегляния")
    files = [f for f in downloads.iterdir() if f.is_file() and not f.name.endswith((".crdownload", ".part", ".tmp"))]
    if not files:
        return "Папка „Изтегляния“ е празна."
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return _describe(files, "Последно изтеглени", limit=5)


@jarvis_tool
def rename_file(number: int, new_name: str) -> str:
    """Преименува файл от последния списък.

    Args:
        number: Номерът на файла в списъка.
        new_name: Новото име (разширението се запазва, ако не е дадено).
    """
    path = folders.pick(number)
    clean = re.sub(r'[<>:"/\\|?*]', "", new_name).strip()
    if not Path(clean).suffix:
        clean += path.suffix
    target = path.with_name(clean)
    if target.exists():
        raise FileExistsError(f"вече има файл „{clean}“")
    path.rename(target)
    folders.last_found[number - 1] = target
    return f"Преименувах „{path.name}“ на „{target.name}“."


@jarvis_tool
def copy_file_to(number: int, destination: str) -> str:
    """Копира файл от последния списък в друга папка.

    Args:
        number: Номерът на файла в списъка.
        destination: Къде — "работен плот", "документи" или пълен път.
    """
    path = folders.pick(number)
    target = shutil.copy2(path, _target_folder(destination))
    return f"Копирах „{path.name}“ в {Path(target).parent.name}."


@jarvis_tool
def move_file_to(number: int, destination: str) -> str:
    """Премества файл от последния списък в друга папка.

    Args:
        number: Номерът на файла в списъка.
        destination: Къде — "работен плот", "документи" или пълен път.
    """
    path = folders.pick(number)
    folder = _target_folder(destination)
    if (folder / path.name).exists():
        raise FileExistsError(f"в „{folder.name}“ вече има файл „{path.name}“")
    target = Path(shutil.move(str(path), str(folder)))
    folders.last_found[number - 1] = target
    return f"Преместих „{path.name}“ в {target.parent.name}."


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]


def _to_recycle_bin(path: Path) -> None:
    """Изтриване в Кошчето — може да се върне оттам."""
    op = _SHFILEOPSTRUCTW(wFunc=3, pFrom=str(path) + "\0",  # FO_DELETE
                          fFlags=0x40 | 0x10 | 0x4 | 0x400)  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) != 0:
        raise OSError(f"не успях да изтрия {path.name}")


@jarvis_tool
def delete_file(number: int) -> str:
    """Изтрива файл от последния списък — в Кошчето (може да се върне). Сър потвърждава с бутон.

    Args:
        number: Номерът на файла в списъка.
    """
    path = folders.pick(number)
    if not confirm.ask("Изтриване на файл", f"{path.name} · {folders.human_size(path.stat().st_size)}",
                       f"{path}\n\nФайлът отива в Кошчето — може да се върне оттам.", "Изтрий"):
        return "Сър отказа — файлът остава."
    _to_recycle_bin(path)
    folders.last_found.pop(number - 1)
    return f"Изтрих „{path.name}“ (в Кошчето е)."


@jarvis_tool
def zip_folder(location: str) -> str:
    """Архивира папка в .zip файл на работния плот.

    Args:
        location: Папката — "документи", пълен път и т.н.
    """
    folder = _target_folder(location)
    desktop = folders.known()["работен плот"]
    archive = shutil.make_archive(str(desktop / f"{folder.name}-{datetime.now():%Y%m%d}"), "zip", folder)
    return f"Архивирах „{folder.name}“ в {Path(archive).name} на работния плот ({folders.human_size(Path(archive).stat().st_size)})."


@jarvis_tool
def unzip_file(number: int) -> str:
    """Разархивира .zip файл от последния списък в папка до него.

    Args:
        number: Номерът на архива в списъка.
    """
    path = folders.pick(number)
    if path.suffix.lower() != ".zip":
        raise ValueError("мога да разархивирам само .zip файлове")
    target = path.with_suffix("")
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():  # без пътища извън целевата папка
            if (target / member).resolve().is_relative_to(target.resolve()):
                archive.extract(member, target)
    return f"Разархивирах „{path.name}“ в папка „{target.name}“."


@jarvis_tool
def read_document(number: int = 0, path: str = "") -> str:
    """Прочита текста на документ (PDF, Word, TXT, CSV…), за да го обобщиш или да отговориш за него.

    Args:
        number: Номерът на файла в последния списък.
        path: Или пълен път до файла.
    """
    file = Path(path.strip('"')) if path.strip() else folders.pick(number or 1)
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        text = "\n".join((page.extract_text() or "") for page in PdfReader(str(file)).pages[:20])
    elif suffix == ".docx":
        with zipfile.ZipFile(file) as doc:
            xml = doc.read("word/document.xml").decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml))
    else:
        text = file.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return f"В „{file.name}“ няма текст, който мога да прочета (може би е сканиран)."
    return f"Документ „{file.name}“ ({len(text)} знака):\n{text[:4000]}"


@jarvis_tool
def clean_temp_files() -> str:
    """Почиства временните файлове на Windows (по-стари от ден), за да освободи място на диск C:.
    Сър потвърждава с бутон."""
    temp = Path(tempfile.gettempdir())
    old = time.time() - 86400
    candidates = [f for f in _walk([temp], seconds=10) if "claude" not in f.parts and f.stat().st_mtime < old]
    size = sum(f.stat().st_size for f in candidates if f.exists())
    if not candidates:
        return "Няма стари временни файлове."
    if not confirm.ask("Почистване на временните файлове", f"{len(candidates)} файла · {folders.human_size(size)}",
                       f"Папка: {temp}\nСамо файлове, по-стари от ден. Заетите се пропускат.", "Почисти"):
        return "Сър отказа — нищо не е изтрито."
    freed = 0
    for f in candidates:
        try:
            freed += f.stat().st_size
            f.unlink()
        except OSError:
            continue  # файлът се ползва от програма
    return f"Освободих {folders.human_size(freed)} от временните файлове."


class _SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong), ("i64NumItems", ctypes.c_longlong)]


@jarvis_tool
def empty_recycle_bin() -> str:
    """Изпразва Кошчето (окончателно). Сър потвърждава с бутон."""
    info = _SHQUERYRBINFO(cbSize=ctypes.sizeof(_SHQUERYRBINFO))
    known = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0
    if known and info.i64NumItems == 0:
        return "Кошчето вече е празно."
    summary = f"{info.i64NumItems} неща · {folders.human_size(info.i64Size)}" if known else "Всичко в Кошчето"
    if not confirm.ask("Изпразване на Кошчето", summary, "Изтритото от Кошчето не може да се върне.", "Изпразни"):
        return "Сър отказа — Кошчето остава."
    ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)
    return "Изпразних Кошчето" + (f" — освободени {folders.human_size(info.i64Size)}." if known else ".")
