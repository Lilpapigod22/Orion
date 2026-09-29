"""
Документи: Орион пише и записва Word, PDF, TXT, Excel и PowerPoint — писма, молби, заявления,
декларации, CV, договори, доклади, таблици, презентации. Добавя текст към документ,
превръща в PDF и разпечатва (разпечатването — след бутон от сър).

Текста пише jarvis/writer.py (отделна заявка към модела с правила за писане), а файла
прави jarvis/documents.py. Файловете са в Документи\\Орион, освен ако сър не каже друго.
"""
import os
from pathlib import Path

from jarvis import confirm, documents, folders, jarvis_tool, writer

# Тестовете го подменят, за да не се отварят прозорци.
open_path = os.startfile


def _where(path: Path) -> str:
    """„Документи\\Орион“ вместо целия път."""
    for name, folder in folders.known().items():
        try:
            relative = path.parent.relative_to(folder)
        except ValueError:
            continue
        label = {"работен плот": "работния плот"}.get(name, name.capitalize())
        return label + (f"\\{relative}" if str(relative) != "." else "")
    return str(path.parent)


def _finish(path: Path, open_after: bool, extra: str = "") -> str:
    if open_after:
        open_path(path)
    opened = " и го отворих" if open_after else ""
    return f"Създадох „{path.name}“ в {_where(path)}{opened}.{extra}"


def _pick(number: int, path: str) -> Path:
    """Файлът, за който става дума: пълен път, номер от последния списък или последният документ."""
    if path.strip():
        file = Path(path.strip().strip('"'))
        if not file.exists():
            raise FileNotFoundError(f"няма файл „{path}“")
        return file
    if number:
        return folders.pick(number)
    return documents.last()


@jarvis_tool
def write_document(request: str, file_format: str = "word", title: str = "", location: str = "",
                   open_after: bool = True) -> str:
    """Пише НОВ документ и го записва като файл (Word, PDF или TXT): писмо, молба, заявление,
    декларация, пълномощно, жалба, CV (автобиография), мотивационно писмо, договор, оферта,
    доклад, есе, реферат, покана, обява, план, инструкция… Текста го пишеш ти по молбата на сър.
    Използвай го, когато сър каже „напиши/направи/създай документ, файл, молба…“ — не отваряй
    Word или Notepad за това.

    Args:
        request: Какво да пише — с ВСИЧКИ подробности от сър: вид, до кого, от кого, имена, дати, суми, тон, дължина.
        file_format: "word" (по подразбиране), "pdf" или "txt".
        title: Име на файла (празно — от заглавието на документа).
        location: Папка: "работен плот", "документи", "изтегляния" или пълен път (празно — Документи\\Орион).
        open_after: Да го отвори ли накрая.
    """
    text = writer.compose("document", request)
    blocks = documents.parse(text)
    name = title.strip() or documents.title_of(blocks, "Документ")
    path = documents.target_path(name, documents.extension(file_format), location)
    documents.save(text, path, name)
    preview = " ".join(documents.plain(b.text) for b in blocks if b.text)[:280]
    return _finish(path, open_after, f" {documents.word_count(text)} думи. Начало: {preview}…")


@jarvis_tool
def save_as_document(content: str, title: str, file_format: str = "word", location: str = "",
                     open_after: bool = True) -> str:
    """Записва ГОТОВ текст като документ точно както е — диктовка на сър, списък, текст от
    разговора (напр. последния ти отговор), бележки. За „запиши това във файл“, „сложи го в Word“.

    Args:
        content: Целият текст. Може с # заглавие, - точки и | таблици |.
        title: Име на файла.
        file_format: "word" (по подразбиране), "pdf", "txt" или "md".
        location: Папка: "работен плот", "документи" или пълен път (празно — Документи\\Орион).
        open_after: Да го отвори ли накрая.
    """
    path = documents.target_path(title or documents.title_of(documents.parse(content), "Бележки"),
                                 documents.extension(file_format), location)
    documents.save(content, path, title)
    return _finish(path, open_after, f" {documents.word_count(content)} думи.")


@jarvis_tool
def create_spreadsheet(request: str, data: str = "", title: str = "", location: str = "",
                       open_after: bool = True) -> str:
    """Прави таблица в Excel (.xlsx): бюджет, разходи, график, списък с хора или продукти,
    сравнение, оценки, инвентар… Пишеш я ти по молбата на сър (с формули за сумите), или
    записваш данните, които сър е дал.

    Args:
        request: Каква таблица — колони, редове, периоди, валута и всички данни от сър.
        data: Готови данни (по желание): редове с „|“ или „;“ между колоните, първият ред — заглавията.
        title: Име на файла (празно — от молбата).
        location: Папка: "работен плот", "документи" или пълен път (празно — Документи\\Орион).
        open_after: Да я отвори ли накрая.
    """
    text = data.strip()
    if text and "|" in text and not text.lstrip().startswith("|"):
        text = "\n".join(f"| {line.strip()} |" for line in text.splitlines() if line.strip())
    sheets = documents.sheets_from(text) if text else []
    if not sheets:
        text = writer.compose("spreadsheet", request + (f"\nДанни от сър:\n{data}" if data.strip() else ""))
        sheets = documents.sheets_from(text)
    if not sheets:
        raise ValueError("не успях да съставя таблица — кажете какви колони да има")
    name = title.strip() or (sheets[0][0] if not sheets[0][0].startswith("Лист") else "") or request[:60]
    path = documents.target_path(name, ".xlsx", location)
    documents.to_xlsx(sheets, path, name)
    rows = sum(len(rows) - 1 for _, rows in sheets)
    columns = ", ".join(documents.plain(c) for c in sheets[0][1][0])
    return _finish(path, open_after, f" {len(sheets)} лист(а), {rows} реда. Колони: {columns}.")


@jarvis_tool
def create_presentation(request: str, slides: int = 6, title: str = "", location: str = "",
                        open_after: bool = True) -> str:
    """Прави презентация в PowerPoint (.pptx) по тема на сър: заглавен слайд, слайдове с точки
    и бележки за говорещия.

    Args:
        request: Темата и всичко, което сър иска да има (за кого е, акценти, стил).
        slides: Колко слайда (без заглавния), обикновено 5–8.
        title: Име на файла (празно — заглавието на презентацията).
        location: Папка: "работен плот", "документи" или пълен път (празно — Документи\\Орион).
        open_after: Да я отвори ли накрая.
    """
    text = writer.compose("presentation", request, slides=slides)
    heading, subtitle, items = documents.slides_from(text)
    if not items:
        raise ValueError("не успях да съставя слайдовете — опитайте с по-конкретна тема")
    name = title.strip() or heading or request[:60]
    path = documents.target_path(name, ".pptx", location)
    documents.to_pptx(heading or name, subtitle, items, path)
    return _finish(path, open_after, f" {len(items) + 1} слайда: " + "; ".join(s.title for s in items[:8]) + ".")


@jarvis_tool
def add_to_document(text: str, number: int = 0, path: str = "") -> str:
    """Добавя текст в края на документ (Word, TXT) — по подразбиране на последния, който си създал.
    За „добави още една точка“, „допиши в документа…“.

    Args:
        text: Какво да добави (може с ## раздел и - точки).
        number: Файл от последния списък (0 — последният документ на Орион).
        path: Пълен път до файла (по желание).
    """
    file = _pick(number, path)
    try:
        documents.append(file, text)
    except PermissionError:
        return f"„{file.name}“ е отворен в друга програма — затворете го и ми кажете пак."
    return f"Добавих текста в „{file.name}“."


@jarvis_tool
def convert_to_pdf(number: int = 0, path: str = "", open_after: bool = True) -> str:
    """Превръща Word, Excel, PowerPoint или TXT файл в PDF (запазва се до оригинала).
    По подразбиране — последния документ, който си създал.

    Args:
        number: Файл от последния списък (0 — последният документ на Орион).
        path: Пълен път до файла (по желание).
        open_after: Да отвори ли PDF-а накрая.
    """
    file = _pick(number, path)
    if file.suffix.lower() == ".pdf":
        return f"„{file.name}“ вече е PDF."
    out = documents.office_to_pdf(file)
    return _finish(out, open_after)


@jarvis_tool
def my_documents() -> str:
    """Последните документи, които Орион е създал (Word, PDF, Excel, PowerPoint…) — за „какви
    документи си ми направил“, „отвори последния документ“. След това open_file ги отваря по номер."""
    items = documents.recent()
    if not items:
        return "Още не съм създавал документи."
    folders.last_found[:] = items[:8]
    return "Последните документи: " + "; ".join(
        f"{i}. {p.name} (в {_where(p)})" for i, p in enumerate(items[:8], 1)) + "."


@jarvis_tool
def print_document(number: int = 0, path: str = "", copies: int = 1) -> str:
    """Разпечатва документ на принтера по подразбиране. Сър потвърждава с бутон.
    По подразбиране — последния документ, който си създал.

    Args:
        number: Файл от последния списък (0 — последният документ на Орион).
        path: Пълен път до файла (по желание).
        copies: Колко копия.
    """
    file = _pick(number, path)
    copies = max(1, min(copies, 20))
    if not confirm.ask("Разпечатване", f"{file.name} · {copies} {'копие' if copies == 1 else 'копия'}",
                       "Ще се разпечата на принтера по подразбиране в Windows.", "Разпечатай"):
        return "Сър отказа — не разпечатвам."
    for _ in range(copies):
        os.startfile(file, "print")
    return f"Пратих „{file.name}“ към принтера ({copies} {'копие' if copies == 1 else 'копия'})."
