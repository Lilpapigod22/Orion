"""
Claude на този компютър — два начина:

- ask_claude: Орион пита Claude през Claude Code (командния ред) и чете отговора. Claude има само
  търсене в интернет — не може да пипа файлове и да пуска команди.
- send_to_claude_app: отваря приложението Claude с готов въпрос. Изпраща го сър (Enter) —
  приложението иска това нарочно, за да не се пращат въпроси зад гърба му.
"""
import os
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from jarvis import jarvis_tool

BASE_DIR = Path(__file__).resolve().parent.parent
WORKDIR = BASE_DIR / "memory" / "claude"  # празна папка — Claude няма достъп до файловете на Орион
TIMEOUT = 240
# Пълният последен отговор — приложението го показва в журнала (app.py).
last_answer: str | None = None


def _cli() -> str | None:
    npm = Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd"
    return shutil.which("claude.cmd") or shutil.which("claude") or (str(npm) if npm.is_file() else None)


@jarvis_tool
def ask_claude(question: str) -> str:
    """Пита Claude (по-мощния изкуствен интелект на сър) и връща отговора му. За „попитай Claude…“,
    сложни въпроси, текстове, код, планове — когато сър иска мнението на Claude.

    Args:
        question: Въпросът или задачата за Claude, пълно и ясно.
    """
    global last_answer
    cli = _cli()
    if not cli:
        return "Не намирам Claude Code на този компютър. Мога да отворя приложението Claude с въпроса."
    WORKDIR.mkdir(parents=True, exist_ok=True)
    prompt = f"{question}\n\n(Отговори на езика на въпроса. Ясно и по същество.)"
    try:
        result = subprocess.run(
            [cli, "-p", "--output-format", "text", "--tools", "WebSearch", "WebFetch",
             "--allowedTools", "WebSearch", "WebFetch"],
            input=prompt.encode("utf-8"), capture_output=True, timeout=TIMEOUT, cwd=WORKDIR,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return f"Claude не отговори за {TIMEOUT // 60} минути — опитайте с по-кратък въпрос."
    answer = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0 or not answer:
        error = result.stderr.decode("utf-8", errors="replace").strip()[:300]
        return f"Claude върна грешка: {error or 'празен отговор'}. Може би трябва да влезете в Claude Code."
    last_answer = answer
    try:
        import pyperclip
        pyperclip.copy(answer)
    except Exception:  # noqa: BLE001 — копирането е удобство
        pass
    return (f"Отговорът на Claude:\n{answer[:3000]}\n\n(Преразкажи го на сър накратко и с твои думи. "
            f"Целият отговор е в журнала и е копиран — може да го постави с Ctrl+V.)")


@jarvis_tool
def send_to_claude_app(prompt: str) -> str:
    """Отваря приложението Claude с готов въпрос, за да види сър отговора там. За „напиши на Claude…“,
    „прати на Claude…“. Сър го изпраща с Enter.

    Args:
        prompt: Текстът, който да се напише в Claude.
    """
    if len(prompt) > 1800:
        prompt = prompt[:1800]
    os.startfile("claude://claude.ai/new?q=" + urllib.parse.quote(prompt))  # noqa: S606
    return "Написах го в Claude — прегледайте текста и натиснете Enter, за да го изпратите."
