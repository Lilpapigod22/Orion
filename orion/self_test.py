"""
Test mode — Orion checks itself, finds its mistakes and fixes them.

One round:
  1. Skills. Every skill in orion/self_test_cases.py is run with sample data in a sandbox:
     notes, reminders, alerts and the portfolio are temporary copies, nothing opens on
     screen, the clipboard is restored, every confirmation (email, deletion) is rejected. Dangerous
     skills (shutdown, email, sound, deletion…) are never run.
  2. Understanding. Requests — ready-made ones and new ones Orion invents for its skills — go the
     same way as real ones (reflexes -> language model). The test checks whether it picked the right
     skill. Actions are not executed: a stub only records them instead.
  3. Fixes.
     - A misunderstood request: Orion adds a keyword to skill selection (orion/router.py)
       or rewrites the skill's description — only the text; the code is guaranteed to stay the same.
       The change is kept only if the request is now understood and the older tests still pass.
     - A broken skill: Orion writes new code, checks it in the sandbox against all the file's tests and
       shows it for approval. The code runs with full access to the computer, so the final
       say is sir's — as with any code Orion writes.
  4. Report — in the journal, in logs/self_test.md and out loud.

Orion does not get in sir's way: tests only run while he is quiet. If he speaks, the current request
to the model is cancelled and the test continues later.
"""
import ast
import copy
import importlib.util
import json
import os
import random
import re
import shutil
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from openai import OpenAI

import config

from . import google, reflexes, router, streaming
from .brain import HONEST_FAILURE, READ_ONLY_TOOLS, Brain
from .memory import ConversationMemory
from .reminders import book as reminder_book
from .self_improve import CODER_PROMPT, Proposal, _normalized, extract_code, forge, lessons, validate_skill_code
from .self_test_cases import ASKS, SKILL_CASES, Ask, SkillCase
from .tools import OrionTools, _parse_docstring, registry

MEMORY_DIR = config.BASE_DIR / "memory"
STORE = MEMORY_DIR / "self_tests.json"            # the requests and checks Orion invented itself
REPORT = config.BASE_DIR / "logs" / "self_test.md"
BOX = Path(tempfile.gettempdir()) / "orion_selftest"

ROUND_PAUSE = 10 * 60   # seconds between rounds while test mode is on
SKILLS_EVERY = 3        # skills (network, files) — every 3 rounds; understanding — every round
NEW_ASKS = 8            # for how many skills Orion invents new requests per round
MAX_FIXES = 4           # fixes per round — the rest wait for the next one
IDLE_SECONDS = 20       # tests still wait this long after sir's last request
STORE_LIMIT = 150
MAX_RETRIES = 3         # how many times a test may be interrupted before it is skipped
MAX_TEST_LESSONS = 10   # lessons from test mode (up to 40 in total — the rest are for sir's remarks)

# The sandbox swaps files for the whole program. While it is active, reminders and price
# alerts wait (see app.py -> _reminder_loop) so they do not read or write the test copies.
sandbox_lock = threading.Lock()

# During the understanding check these skills really run — they only read and store nothing.
# All the others are replaced by a stub that only records the call.
LIVE_TOOLS = {
    "get_current_time", "calculate", "get_weather", "days_until_date", "wikipedia", "convert_currency",
    "convert_units", "search_web", "read_webpage", "market_price", "market_overview", "crypto_market",
    "compare_assets", "top_stock_movers", "crypto_fear_greed", "convert_crypto", "weather_week",
    "weather_hourly", "will_it_rain", "air_quality", "uv_index", "date_after_days", "days_between",
    "weekday_of_date", "age_from_birthday", "sunrise_sunset", "moon_phase", "bulgarian_holidays",
    "next_holiday", "name_day", "todays_name_days", "random_number", "flip_coin",  # the password is copied -> stub
    "roll_dice", "pick_random", "count_text", "encode_base64", "decode_base64", "hash_text",
    "convert_number_base", "roman_numeral", "convert_timestamp", "number_stats", "percent_change",
    "split_bill", "loan_payment", "compound_interest", "vat_calculator", "discount_price", "savings_goal",
    "fuel_cost", "bmi_calculator", "translate_text", "detect_language", "define_word", "country_info",
    "distance_between", "my_public_ip", "ping_host", "website_status", "local_network_info", "wifi_info",
    "port_in_use", "dns_lookup", "system_status", "resource_hogs", "running_programs", "windows_version",
    "list_skills", "list_lessons", "radio_stations",
}
STUB = "Изпълнено успешно."
# Orion invents no requests for these: self-improvement is checked separately, not through itself.
NOT_ASKED = {"learn_lesson", "forget_lesson", "create_skill", "improve_skill", "undo_skill_change",
             "recent_errors", "list_lessons", "remember"}
# Network problems are not a code bug — the skill is re-checked but not “fixed”.
NETWORK_RE = re.compile(
    r"URLError|timed out|TimeoutError|ConnectionError|Connection(Reset|Refused|Aborted)|getaddrinfo|"
    r"RemoteDisconnected|HTTP Error (5\d\d|429)|SSLError|IncompleteRead|No route to host|"
    r"temporarily unavailable|Max retries|ReadTimeout|не отговори за", re.IGNORECASE)
# Words found in all kinds of requests — not usable as a keyword for a skill group.
STOP_WORDS = {
    "може", "можеш", "можете", "моля", "искам", "искаш", "колко", "какво", "какъв", "каква", "какви",
    "кажи", "кажете", "митко", "някак", "днес", "утре", "вчера", "сега", "мога", "моят", "моята", "моите",
    "кога", "къде", "дали", "имам", "имаме", "направи", "направете", "покажи", "пусни", "отвори",
    "провери", "намери", "трябва", "нещо", "нужно", "много", "малко", "беше", "бъде", "ще", "който",
    "която", "което", "които", "този", "тази", "това", "тези", "онзи", "някой", "всички", "всеки",
    "защо", "как", "пак", "още", "вече", "също", "само", "добре", "благодаря", "здравей", "дай",
}

GENERATE_PROMPT = """Ти пишеш тестове за гласовия асистент Орион. Ето едно от уменията му:
име: {name}
описание: {description}

Измисли {count} различни молби, с които човек на глас би помолил Орион за точно това.
- естествен разговорен български, до 14 думи, както говорят хората;
- с конкретни стойности (град, число, дата, име), ако умението има нужда от тях;
- без името на умението и без технически думи;
- всяка молба с различни думи.
Отговори САМО с JSON масив от низове."""

JUDGE_PROMPT = """Молба към гласовия асистент: „{phrase}“
Асистентът използва умението {used} — {description}
Изпълнява ли това умение молбата правилно? (Че и друго умение би свършило работа, няма значение.)
Отговори само с ДА или НЕ."""

DESCRIBE_PROMPT = """Подобряваш описанието на едно умение на гласовия асистент Орион. Моделът, който избира
уменията по описанията им, не разбра, че тези молби са за това умение:
{phrases}
Вместо това: {what_happened}

Умение: {name}
Сегашно описание: {description}
{others}
Напиши ново описание — 1 до 3 изречения, до 350 знака, на български: какво прави умението и КОГА
да се използва, с 2–3 кратки примерни молби в кавички „…“ (една от тях като горните). Запази всичко
вярно от сегашното описание. Отговори САМО с новото описание."""

KEYWORD_PROMPT = """Молба към асистента: „{phrase}“
Тя е за тази група умения: {tools}.
Коя ЕДНА дума от молбата най-ясно показва, че става дума точно за тази група (а не за нещо друго)?
Отговори само с думата, така както е написана в молбата."""

SENSIBLE_PROMPT = """Умение на гласов асистент: {name} — {description}
Молба: „{phrase}“
Смислена ли е молбата (така говорят хората) и може ли точно това умение да я изпълни?
Отговори само с ДА или НЕ."""

LESSON_PROMPT = """Гласовият асистент Орион не използва умението {tool} за молбата „{phrase}“ — {what}.
Какво прави {tool}: {description}
Напиши ЕДНО кратко общо правило (до 25 думи, повелително наклонение, на български), което да му
напомня кога да използва {tool}, вместо да отговаря сам. Правилото трябва да съдържа името {tool}.
Отговори само с правилото."""

INVENT_PROMPT = """Умение на гласовия асистент Орион (JSON схема):
{schema}
Измисли реалистични стойности на параметрите за една проверка дали умението работи.
Отговори САМО с JSON обект (параметър -> стойност)."""

FIX_TASK = """Тест режимът откри грешка в умение. Поправи файла.

Проверка: {tool}({args})
Проблем: {problem}
{trace}
Всички проверки на този файл — след поправката трябва да минават:
{cases}

Текущ файл {file}:
```python
{code}```"""


class Stopped(Exception):
    """Sir turned test mode off."""


class Interrupted(Exception):
    """Sir started talking — the current test is cancelled and re-run later."""


class StoppableClient:
    """An OpenAI client for test mode. The answer arrives in parts (stream) and between every two parts
    it checks whether sir has started talking — then the stream is closed, Ollama stops generating
    and sir's answer does not wait for the test. Returns the same kind of answer as the normal client
    (content, tool_calls, reasoning), so Brain can use it too."""

    def __init__(self, check: "Callable[[], type[Exception] | None]"):
        self._client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=240, max_retries=0)
        self._check = check  # None — carry on; Interrupted/Stopped — stop
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        return streaming.create_streamed(self._client, check=self._check, **kwargs)


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _json_in(text: str, opener: str):
    """The first JSON array/object in the model's answer (or None)."""
    closer = "]" if opener == "[" else "}"
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    start, end = text.find(opener), text.rfind(closer)
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


# =====================================================================================
#  Sandbox
# =====================================================================================
class Sandbox:
    """While active, skills only touch temporary copies: the data files from memory/ are
    in BOX, nothing opens on screen, remembered lists and the clipboard are restored afterwards,
    and every confirmation (email, deletion) is rejected."""

    SKIP = {"orion.self_test", "orion.router", "orion.self_improve"}

    def __enter__(self):
        sandbox_lock.acquire()
        self._attrs: list[tuple[object, str, object]] = []
        self._containers: list[tuple[object, object]] = []
        self._clipboard = None
        try:
            self._enter()
        except BaseException:
            self._leave()
            sandbox_lock.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            self._leave()
        finally:
            sandbox_lock.release()
        return False

    def _set(self, obj, attr: str, value) -> None:
        self._attrs.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    def _enter(self) -> None:
        BOX.mkdir(parents=True, exist_ok=True)
        # Opening files and websites is blocked everywhere — including where a module saved it
        # under another name (e.g. `open_path = os.startfile`).
        openers = {id(f) for f in (getattr(os, "startfile", None), webbrowser.open, webbrowser.open_new,
                                   webbrowser.open_new_tab) if f}
        for name, module in list(sys.modules.items()):
            if module is None or name in self.SKIP or not name.startswith(("skills.", "orion.")):
                continue
            for attr, value in list(vars(module).items()):
                if attr.startswith("__"):
                    continue
                if id(value) in openers:
                    self._set(module, attr, lambda *args, **kwargs: None)
                elif isinstance(value, Path) and value.suffix == ".json" and MEMORY_DIR in value.parents:
                    self._set(module, attr, BOX / value.name)
                elif name.startswith("skills.") or name in ("orion.folders", "orion.reels"):
                    if attr.startswith(("last_", "_last")):  # “the last list of files/emails…”
                        self._attrs.append((module, attr, value))
                    if isinstance(value, (list, dict, set)):
                        self._containers.append((value, copy.copy(value)))
        self._set(reminder_book, "path", BOX / "reminders.json")
        from . import confirm
        self._set(confirm, "handler", lambda *args, **kwargs: False)
        self._set(os, "startfile", lambda *args, **kwargs: None)
        for attr in ("open", "open_new", "open_new_tab"):
            self._set(webbrowser, attr, lambda *args, **kwargs: True)
        try:
            import pyperclip
            self._clipboard = pyperclip.paste()
        except Exception:  # noqa: BLE001 — the test still runs without a clipboard
            self._clipboard = None

    def _leave(self) -> None:
        for container, saved in reversed(self._containers):
            try:
                container.clear()
                container.update(saved) if not isinstance(container, list) else container.extend(saved)
            except Exception:  # noqa: BLE001
                pass
        for obj, attr, value in reversed(self._attrs):
            setattr(obj, attr, value)
        if self._clipboard is not None:
            try:
                import pyperclip
                pyperclip.copy(self._clipboard)
            except Exception:  # noqa: BLE001
                pass


# A skill that does something outside (email, deletion, opening…) is never run with invented data.
ACTION_WORDS = re.compile(
    r"изпра|прати|праща|пише на|трие|изтри|премахва|маха|купува|плаща|публикува|качва|изключва|рестарт|"
    r"затваря|отваря|пуска|стартира|печат|принт|запис|създава|добавя|сменя|променя|"
    r"send|post|delete|upload|print|write|open", re.IGNORECASE)


def _may_invent(name: str) -> bool:
    """Whether Orion may invent and run a check for the skill itself: only if it wrote it itself
    (the built-in skills have hand-written checks in self_test_cases.py) and it only reads — no writing
    files, no programs, no sending data and no action words in the description."""
    path = registry.source_file(name)
    if name in NOT_ASKED or name not in registry.names() or not path or not path.exists():
        return False
    if not any(forge.history_dir.glob(f"{path.stem}__*.created")):  # not written by Orion
        return False
    code = path.read_text(encoding="utf-8")
    problems, warnings, _ = validate_skill_code(code, set())
    if problems or set(warnings) - {"достъп до интернет"}:
        return False
    if re.search(r"startfile|\b(?:data|method)\s*=|urlopen\([^)]*,\s*[^t)]", code):  # opening, sending data
        return False
    return not ACTION_WORDS.search(registry._tools[name]["schema"]["function"]["description"])


def _call(tools, name: str, args: dict, timeout: float = 60.0) -> str:
    """The skill on a separate thread — if it hangs, the test moves on (and records the error)."""
    box: dict[str, str] = {}
    worker = threading.Thread(target=lambda: box.update(result=tools.call(name, args)), daemon=True,
                              name=f"selftest-{name}")
    worker.start()
    worker.join(timeout)
    return box.get("result", f"Грешка при изпълнение на '{name}': TimeoutError: не отговори за {timeout:.0f} секунди")


def _problem(case: SkillCase, result: str) -> str | None:
    """What is wrong with the result (or None)."""
    if result.startswith("Грешка"):
        return result.split(": ", 1)[-1]
    if not result.strip():
        return "върна празен резултат"
    if case.expect and not re.search(case.expect, result):
        return f"резултатът не съдържа очакваното ({case.expect}): „{result[:140]}“"
    return None


def _resolved(args: dict) -> dict:
    return {k: v.replace("{box}", str(BOX)) if isinstance(v, str) else v for k, v in args.items()}


# =====================================================================================
#  The registry the test “brain” sees
# =====================================================================================
class TestTools:
    """Only LIVE_TOOLS are real, the other skills are stubs. Optionally — different descriptions
    of the skills, to test a description fix before it is saved."""

    def __init__(self, descriptions: dict[str, str] | None = None):
        self.descriptions = descriptions or {}
        self.calls: list[str] = []

    def names(self) -> list[str]:
        return registry.names()

    def schemas(self, exclude_modules=frozenset()) -> list[dict]:
        schemas = registry.schemas(exclude_modules)
        if not self.descriptions:
            return schemas
        changed = []
        for schema in schemas:
            name = schema["function"]["name"]
            if name in self.descriptions:
                schema = copy.deepcopy(schema)
                schema["function"]["description"] = self.descriptions[name]
            changed.append(schema)
        return changed

    def call(self, name: str, arguments) -> str:
        self.calls.append(name)
        if name not in registry.names():
            return f"Грешка: няма умение с име '{name}'."
        return registry.call(name, arguments) if name in LIVE_TOOLS else STUB


@dataclass
class AskResult:
    ask: Ask
    used: list[str]
    answer: str
    problem: str | None
    via: str

    @property
    def ok(self) -> bool:
        return self.problem is None


def _evaluate(ask: Ask, used: list[str], answer: str, via: str) -> AskResult:
    problem = None
    names = list(dict.fromkeys(used))
    if ask.expect:
        if not used:
            problem = "не извика умение"
        elif not set(used) & set(ask.expect):
            problem = f"извика {', '.join(names)} вместо {' или '.join(ask.expect)}"
    else:
        acted = [u for u in names if u not in READ_ONLY_TOOLS and u not in LIVE_TOOLS]
        if acted:
            problem = f"извика {', '.join(acted)} без нужда"
    if problem is None and answer.strip() == HONEST_FAILURE:
        problem = "отговори, че не е успял"
    if problem is None and not answer.strip():
        problem = "върна празен отговор"
    if problem is None and ask.answer and not re.search(ask.answer, answer):
        problem = f"грешен отговор: „{answer[:120]}“"
    return AskResult(ask, used, answer, problem, via)


# =====================================================================================
#  Description fix: only the docstring text; the code stays the same
# =====================================================================================
def _shape(code: str) -> str:
    """The code without docstrings — to prove that only the text changed."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:]
    return ast.dump(tree)


def replace_description(code: str, func: str, description: str) -> str:
    """The same file, but with a new description for the skill `func` (the “Args:” section stays)."""
    tree = ast.parse(code)
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if fn is None or not fn.body or not isinstance(fn.body[0], ast.Expr) \
            or not isinstance(fn.body[0].value, ast.Constant) or not isinstance(fn.body[0].value.value, str):
        raise ValueError(f"не намирам описанието на „{func}“")
    doc = fn.body[0]
    _, has_args, args = (ast.get_docstring(fn) or "").partition("Args:")
    indent = " " * (fn.col_offset + 4)
    text = description.replace("\\", "/").replace('"""', "„").strip()
    wrapped = textwrap.wrap(text, width=max(40, 100 - len(indent))) or [text]
    lines = [f'{indent}"""{wrapped[0]}'] + [indent + part for part in wrapped[1:]]
    if has_args:
        lines += ["", f"{indent}Args:"] + [(indent + line) if line.strip() else ""
                                           for line in args.strip("\n").split("\n")]
        lines.append(f'{indent}"""')
    elif len(lines) == 1:
        lines[0] += '"""'
    else:
        lines.append(f'{indent}"""')
    source = code.splitlines()
    new_code = "\n".join(source[:doc.lineno - 1] + lines + source[doc.end_lineno:]) + "\n"
    if _shape(new_code) != _shape(code):  # should never happen — but if it does, nothing is saved
        raise ValueError("промяната засяга не само описанието")
    return new_code


# =====================================================================================
#  Report
# =====================================================================================
@dataclass
class Report:
    number: int
    started: datetime = field(default_factory=datetime.now)
    skills_total: int = 0
    skills_ok: int = 0
    skill_failures: list[tuple[SkillCase, str, bool]] = field(default_factory=list)  # (test, problem, network)
    asks_total: int = 0
    asks_ok: int = 0
    ask_failures: list[AskResult] = field(default_factory=list)
    new_asks: int = 0
    fixes: list[tuple[str, str]] = field(default_factory=list)  # („сам“/„одобрена“/…, description)
    untested: list[str] = field(default_factory=list)
    stopped: bool = False

    def count(self, *kinds: str) -> int:
        return sum(1 for kind, _ in self.fixes if kind in kinds)

    def summary(self) -> str:
        parts = []
        if self.skills_total:
            parts.append(f"проверих {_count(self.skills_total, 'умение', 'умения')} — работят {self.skills_ok}")
        if self.asks_total:
            parts.append(f"разбрах правилно {self.asks_ok} от {_count(self.asks_total, 'молба', 'молби')}")
        text = "; ".join(parts) or "не успях да проверя нищо"
        fixed = self.count("сам", "одобрена")
        if fixed:
            text += f". Поправих {_count(fixed, 'грешка', 'грешки')}"
        unfixed = self.count("неуспешна", "ядро", "отказана")
        if unfixed:
            text += f". {_count(unfixed, 'проблем остава', 'проблема остават')} — подробности в журнала"
        return text + "."

    def markdown(self) -> str:
        lines = [f"# Самопроверка на Орион — кръг {self.number}, {self.started:%d.%m.%Y %H:%M}", ""]
        if self.stopped:
            lines += ["_Прекъсната от сър — резултатите са частични._", ""]
        lines += [self.summary(), ""]
        if self.skill_failures:
            lines += ["## Умения с проблем", ""]
            for case, problem, network in self.skill_failures:
                tag = " (мрежа — временно)" if network else ""
                lines.append(f"- `{case.tool}({json.dumps(case.args, ensure_ascii=False)})`{tag}: {problem}")
            lines.append("")
        if self.ask_failures:
            lines += ["## Неразбрани молби", ""]
            for r in self.ask_failures:
                lines.append(f"- „{r.ask.phrase}“ ({r.ask.source} тест, {r.via}): {r.problem}")
            lines.append("")
        if self.fixes:
            lines += ["## Поправки", ""] + [f"- {kind}: {text}" for kind, text in self.fixes] + [""]
        if self.untested:
            lines += ["## Без проверка на кода (само разбиране)", "", ", ".join(sorted(self.untested)), ""]
        return "\n".join(lines)


# =====================================================================================
#  Test mode
# =====================================================================================
class SelfTester:
    """`host` is the app (app.py -> Orion): brain, work_lock, hud(), say(), test_idle(),
    approve_test_fix(). work_lock is the lock the worker also holds while answering sir:
    so a sandbox test and a real request never run at the same time."""

    def __init__(self, host):
        self.host = host
        self.enabled = False
        self.thread: threading.Thread | None = None
        self.client = StoppableClient(self._stop_reason)
        self.last_report: Report | None = None
        self.rounds = 0

    # --- Switching on ------------------------------------------------------------------------
    def start(self) -> bool:
        """Turns test mode on. False if it is already running."""
        if self.enabled and self.thread and self.thread.is_alive():
            return False
        self.enabled = True
        self.thread = threading.Thread(target=self._loop, daemon=True, name="selftest")
        self.thread.start()
        return True

    def stop(self) -> None:
        self.enabled = False

    @property
    def running(self) -> bool:
        return bool(self.enabled and self.thread and self.thread.is_alive())

    # --- Link to the window ------------------------------------------------------------------
    def _hud(self, fn: str, *args) -> None:
        try:
            self.host.hud(fn, *args)
        except Exception:  # noqa: BLE001 — the window may be closing
            pass

    def _log(self, text: str) -> None:
        print(f"[Тест] {text}")
        self._hud("addLog", "test", text)

    def _progress(self, text: str, active: bool = True) -> None:
        self._hud("setTest", {"active": active, "text": text})

    def _task(self, key: str, tool: str, label: str) -> None:
        entry = registry._tools.get(tool, {})
        self._hud("toolStart", key, {}, entry.get("module", ""), label[:46])

    def _task_done(self, key: str, text: str, ok: bool) -> None:
        self._hud("toolDone", key, text[:200], ok)

    # --- Waiting for sir ----------------------------------------------------------------------
    def _wait_idle(self) -> None:
        """Waits until sir is not talking and Orion is idle. Stopped — if test mode was turned off."""
        while self.enabled and not self.host.test_idle():
            time.sleep(0.5)
        if not self.enabled:
            raise Stopped()

    def _stop_reason(self) -> type[Exception] | None:
        """For StoppableClient: stops the request if sir started talking or turned test mode off."""
        if not self.enabled:
            return Stopped
        return None if self.host.test_idle() else Interrupted

    def _retrying(self, action, *args):
        """Runs `action`; if sir interrupts it — waits for quiet and tries again."""
        for _ in range(MAX_RETRIES):
            self._wait_idle()
            try:
                return action(*args)
            except Interrupted:
                continue
        raise Interrupted()

    def _complete(self, prompt: str, temperature: float = 0.2, effort: str | None = "none",
                  system: str | None = None) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        reply = self.client.chat.completions.create(
            model=self.host.brain.model, messages=messages, temperature=temperature,
            **({"reasoning_effort": effort} if config.LLM_REASONING_EFFORT and effort else {}))
        return re.sub(r"<think>.*?</think>", "", reply.choices[0].message.content or "", flags=re.DOTALL).strip()

    # --- The main loop -----------------------------------------------------------------------
    def _loop(self) -> None:
        while self.enabled:
            self.rounds += 1
            report = Report(self.rounds)
            try:
                self._round(report)
            except Stopped:
                report.stopped = True
            except Exception as e:  # noqa: BLE001 — an error in the test itself must not stop Orion
                traceback.print_exc()
                self._log(f"Самопроверката спря заради грешка: {type(e).__name__}: {e}")
                report.stopped = True
            finally:
                shutil.rmtree(BOX, ignore_errors=True)
            self._finish(report)
            wake = time.time() + ROUND_PAUSE
            while self.enabled and time.time() < wake:
                time.sleep(1)
        self._progress("", active=False)

    def _round(self, report: Report) -> None:
        store = self._load_store()
        first = report.number == 1
        self._hud("thought", "Самопроверка: пускам уменията си в пясъчник и проверявам дали разбирам молбите.")
        if report.number % SKILLS_EVERY == 1:
            self._check_skills(report, store)
        self._check_understanding(report, store, invent=True)
        self._save_store(store)
        self._fix(report, store)
        self._save_store(store)
        if first:
            report.untested = self._untested(store)

    # --- 1. Skills ----------------------------------------------------------------------------
    def _skill_cases(self, store: dict) -> list[SkillCase]:
        names = set(registry.names())
        cases = [c for c in SKILL_CASES if c.tool in names and (c.needs != "google" or google.is_connected())]
        cases += [SkillCase(s["tool"], s["args"]) for s in store["skills"] if s["tool"] in names and _may_invent(s["tool"])]
        return cases

    def _check_skills(self, report: Report, store: dict) -> None:
        self._invent_skill_cases(store)
        cases = self._skill_cases(store)
        # By module: the tests of one file run together in one sandbox (write -> read).
        modules: dict[str, list[SkillCase]] = {}
        for case in cases:
            modules.setdefault(registry._tools[case.tool]["module"], []).append(case)
        shutil.rmtree(BOX, ignore_errors=True)
        report.skills_total = len({c.tool for c in cases})
        done, failed = 0, []
        self._log(f"Започвам: {_count(len(cases), 'проверка', 'проверки')} на "
                  f"{_count(report.skills_total, 'умение', 'умения')} в пясъчник.")
        for group in modules.values():
            self._wait_idle()
            with self.host.work_lock, Sandbox():
                for case in group:
                    done += 1
                    self._progress(f"skills {done}/{len(cases)}")
                    problem = self._run_skill_case(case, f"test:{done}")
                    if problem:
                        failed.append((case, problem))
        # The network is sometimes slow — failed ones are checked once more.
        for case, problem in failed:
            self._wait_idle()
            with self.host.work_lock, Sandbox():
                passed = self._run_skill_case(case, f"test:again:{case.tool}") is None
            if passed:
                continue
            network = bool(NETWORK_RE.search(problem))
            report.skill_failures.append((case, problem, network))
            self._log(f"✗ {case.tool}: {problem[:200]}" + (" (мрежа — вероятно временно)" if network else ""))
        report.skills_ok = report.skills_total - len({c.tool for c, _, _ in report.skill_failures})

    def _run_skill_case(self, case: SkillCase, key: str, tools=registry) -> str | None:
        self._task(key, case.tool, f"тест · {case.tool}")
        try:
            if case.setup:
                case.setup(BOX)
            result = _call(tools, case.tool, _resolved(case.args))
        except Exception as e:  # noqa: BLE001 — broken set-up = failed test
            result = f"Грешка при подготовката: {type(e).__name__}: {e}"
        problem = _problem(case, result)
        self._task_done(key, "работи" if problem is None else problem, problem is None)
        return problem

    def _invent_skill_cases(self, store: dict) -> None:
        """New skills Orion wrote itself have no ready-made check — it invents data
        for a test. Only if the skill only reads (see _may_invent): otherwise it would really send,
        delete or open something."""
        covered = {c.tool for c in SKILL_CASES} | {s["tool"] for s in store["skills"]} | set(store["no_case"])
        for name in registry.names():
            if name in covered:
                continue
            if not _may_invent(name):
                store["no_case"].append(name)
                continue
            schema = registry._tools[name]["schema"]["function"]
            try:
                args = _json_in(self._retrying(self._complete, INVENT_PROMPT.format(
                    schema=json.dumps(schema, ensure_ascii=False))), "{")
            except Interrupted:
                continue
            props, required = schema["parameters"]["properties"], schema["parameters"]["required"]
            if isinstance(args, dict) and set(args) <= set(props) and set(required) <= set(args):
                store["skills"].append({"tool": name, "args": args})
                self._log(f"Написах си нова проверка: {name}({json.dumps(args, ensure_ascii=False)})")

    # --- 2. Understanding ---------------------------------------------------------------------
    def _all_asks(self, store: dict) -> list[Ask]:
        names = set(registry.names())
        asks = [a for a in ASKS if not a.expect or set(a.expect) & names]
        asks += [Ask(s["phrase"], tuple(s["expect"]), None, "мой") for s in store["asks"]
                 if set(s["expect"]) & names]
        return asks

    def _check_understanding(self, report: Report, store: dict, invent: bool) -> None:
        if invent:
            report.new_asks = self._invent_asks(store)
        asks = self._all_asks(store)
        report.asks_total = len(asks)
        self._log(f"Проверявам дали разбирам {_count(len(asks), 'молба', 'молби')} "
                  f"({report.new_asks} от тях измислих сега).")
        for i, ask in enumerate(asks, 1):
            self._progress(f"understanding {i}/{len(asks)}")
            key = f"test:ask:{i}"
            main = ask.expect[0] if ask.expect else "list_skills"
            self._task(key, main, f"разбирам ли „{ask.phrase}“")
            try:
                result = self._retrying(self._run_ask, ask)
            except Interrupted:
                self._task_done(key, "прекъснат", True)
                report.asks_total -= 1
                continue
            if not result.ok and ask.source == "мой" and result.used:
                result = self._second_opinion(result, store)
            self._task_done(key, "разбрах" if result.ok else result.problem, result.ok)
            self._remember_result(store, result)
            if result.ok:
                report.asks_ok += 1
            else:
                report.ask_failures.append(result)
                self._log(f"✗ „{ask.phrase}“ — {result.problem}")

    def _run_ask(self, ask: Ask, descriptions: dict[str, str] | None = None,
                 routes: dict[str, list[str]] | None = None, lesson: str | None = None) -> AskResult:
        """The request goes the way real ones do: reflex -> model. Actions are stubs.
        descriptions/routes/lesson — a fix on trial before it is saved."""
        tools = TestTools(descriptions)
        reflex = reflexes.respond(ask.phrase)
        if reflex and reflex.tool:
            result = tools.call(reflex.tool, reflex.arguments_json)
            return _evaluate(ask, tools.calls, reflex.answer or result, "рефлекс")
        if reflex and not reflex.action:  # time, date, day
            return _evaluate(ask, ["get_current_time"], reflex.answer, "рефлекс")
        if reflex:
            return _evaluate(ask, [], f"({reflex.action})", "рефлекс")
        answer = self._test_brain(tools, routes, lesson).think(ask.phrase)  # Interrupted if sir starts talking
        return _evaluate(ask, tools.calls, answer, "модел")

    def _test_brain(self, tools: TestTools, routes: dict | None, lesson: str | None = None) -> Brain:
        source = self.host.brain
        def with_lesson() -> str:  # the lesson on trial — after the ones learned so far
            base = source.extra_prompt() if source.extra_prompt else ""
            if not base:
                return f"Поуки от минали грешки — спазвай ги винаги, те са по-важни от примерите:\n1. {lesson}"
            return f"{base}\n{len(lessons.all()) + 1}. {lesson}"

        extra = with_lesson if lesson else source.extra_prompt
        brain = Brain(tools, source.knowledge, ConversationMemory(4), base_url=config.LLM_BASE_URL,
                      api_key=config.LLM_API_KEY, model=source.model, persona=source.persona,
                      temperature=source.temperature, max_tool_rounds=source.max_tool_rounds,
                      extra_prompt=extra, after_turn=None,
                      reasoning_effort=source.reasoning_effort,
                      deep_reasoning_effort=source.deep_reasoning_effort)
        brain.client = self.client
        brain.stream = False  # the client streams (and stops) by itself
        brain.route_extra = routes
        return brain

    def _second_opinion(self, result: AskResult, store: dict) -> AskResult:
        """The invented request got a different skill — maybe that is right too („времето утре“
        -> get_weather instead of will_it_rain). Orion judges; if it is right, it is accepted from now on."""
        used = next((u for u in result.used if u in registry.names()), None)
        if not used:
            return result
        description = registry._tools[used]["schema"]["function"]["description"][:300]
        try:
            verdict = self._retrying(self._complete, JUDGE_PROMPT.format(
                phrase=result.ask.phrase, used=used, description=description), 0.0)
        except Interrupted:
            return result
        if not verdict.upper().startswith("ДА"):
            return result
        for item in store["asks"]:
            if item["phrase"] == result.ask.phrase and used not in item["expect"]:
                item["expect"].append(used)
        return AskResult(result.ask, result.used, result.answer, None, result.via)

    def _invent_asks(self, store: dict) -> int:
        """Orion invents new requests for the skills that have been tested least so far."""
        coverage: dict[str, int] = {}
        for ask in [*ASKS, *(Ask(s["phrase"], tuple(s["expect"])) for s in store["asks"])]:
            for tool in ask.expect[:1]:
                coverage[tool] = coverage.get(tool, 0) + 1
        candidates = [n for n in registry.names() if n not in NOT_ASKED]
        random.shuffle(candidates)
        candidates.sort(key=lambda n: coverage.get(n, 0))
        known = {s["phrase"].lower() for s in store["asks"]} | {a.phrase.lower() for a in ASKS}
        added = 0
        for i, name in enumerate(candidates[:NEW_ASKS], 1):
            self._progress(f"writing new tests {i}/{NEW_ASKS}")
            description = registry._tools[name]["schema"]["function"]["description"][:500]
            try:
                phrases = _json_in(self._retrying(self._complete, GENERATE_PROMPT.format(
                    name=name, description=description, count=2), 0.8), "[")
            except Interrupted:
                continue
            for phrase in phrases if isinstance(phrases, list) else []:
                if not isinstance(phrase, str):
                    continue
                phrase = phrase.strip().strip("„“\"'")
                if (not 6 <= len(phrase) <= 160 or not re.search(r"[а-яА-Я]", phrase)
                        or name in phrase or phrase.lower() in known):
                    continue
                try:  # a nonsense request („Заправи гласа на пълна сила“) would lead to a nonsense “fix”
                    sensible = self._retrying(self._complete, SENSIBLE_PROMPT.format(
                        name=name, description=description[:300], phrase=phrase), 0.0)
                except Interrupted:
                    continue
                if not sensible.upper().startswith("ДА"):
                    continue
                known.add(phrase.lower())
                store["asks"].append({"phrase": phrase, "expect": [name], "added": f"{datetime.now():%d.%m.%Y}",
                                      "passed": 0, "failed": 0})
                added += 1
        if added:
            self._log(f"Написах си {_count(added, 'нова молба', 'нови молби')} за проверка.")
        return added

    @staticmethod
    def _remember_result(store: dict, result: AskResult) -> None:
        for item in store["asks"]:
            if item["phrase"] == result.ask.phrase:
                item["passed" if result.ok else "failed"] += 1
                item["last"] = "ok" if result.ok else result.problem

    # --- 3. Fixes -----------------------------------------------------------------------------
    def _fix(self, report: Report, store: dict) -> None:
        budget = MAX_FIXES
        # Understanding: one skill at a time (several misunderstood requests for one skill — one fix).
        by_tool: dict[str, list[AskResult]] = {}
        for result in report.ask_failures:
            if result.problem.startswith("грешен отговор") and set(result.used) & set(result.ask.expect):
                # The skill is the right one — the answer itself is wrong (e.g. a fact). A description does not help.
                report.fixes.append(("неуспешна", f"„{result.ask.phrase}“ — използвах правилното умение, "
                                                  f"но отговорих грешно: {result.answer[:140]}"))
            elif result.ask.expect and result.via == "модел":
                by_tool.setdefault(result.ask.expect[0], []).append(result)
            elif result.via == "рефлекс":
                report.fixes.append(("ядро", f"„{result.ask.phrase}“ се хваща от бързите команди (рефлекси) — "
                                             f"това е в ядрото и не го променям сам."))
        for tool, results in by_tool.items():
            if budget <= 0:
                break
            budget -= 1
            try:
                self._fix_understanding(tool, results, report, store)
            except Interrupted:
                report.fixes.append(("неуспешна", f"{tool}: поправката беше прекъсната — ще опитам пак."))
        # The skills' code.
        broken: dict[str, list[tuple[SkillCase, str]]] = {}
        for case, problem, network in report.skill_failures:
            if not network:
                broken.setdefault(case.tool, []).append((case, problem))
        for tool, failures in broken.items():
            if budget <= 0:
                break
            budget -= 1
            try:
                self._fix_code(tool, failures, report, store)
            except Interrupted:
                report.fixes.append(("неуспешна", f"{tool}: поправката беше прекъсната — ще опитам пак."))

    def _passes(self, ask: Ask, times: int = 1, **overrides) -> bool:
        for _ in range(times):
            if not self._retrying(self._run_ask, ask, overrides.get("descriptions"), overrides.get("routes"),
                                  overrides.get("lesson")).ok:
                return False
        return True

    def _regressions(self, tools: set[str], store: dict, exclude: set[str], words: list[str] | None = None) -> list[Ask]:
        """The requests a fix might affect — they must keep passing."""
        asks = [a for a in self._all_asks(store) if a.phrase not in exclude]
        near = [a for a in asks if set(a.expect) & tools]
        if words:
            near += [a for a in asks if any(w in a.phrase.lower() for w in words) and a not in near]
        return near[:6]

    def _fix_understanding(self, tool: str, results: list[AskResult], report: Report, store: dict) -> None:
        path = registry.source_file(tool)
        module = registry._tools.get(tool, {}).get("module", "")
        if not path or path.name in forge.PROTECTED:
            return
        self._progress(f"fixing · {tool}")
        self._hud("thought", f"Не разбрах „{results[0].ask.phrase}“ — търся защо и как да се поправя.")
        target, phrases = results[0].ask, {r.ask.phrase for r in results}
        wrong = {u for r in results for u in r.used if u in registry.names() and u != tool}
        # Compared only with the requests that passed in this round.
        failing = {r.ask.phrase for r in report.ask_failures}
        regressions = self._regressions({tool, *wrong}, store, failing)

        # a) The skill's group was hidden for this request -> a keyword for selection.
        routes = None
        if module in router.excluded_modules(target.phrase):
            word = self._keyword(target.phrase, tool, module)
            if word:
                routes = {module: [word]}
                extra = self._regressions(set(), store, failing, [word])
                if self._passes(target, 3, routes=routes) and all(self._passes(a, routes=routes) for a in extra):
                    router.learn(module, word)
                    report.fixes.append(("сам", f"„{target.phrase}“ — научих, че думата „{word}“ означава "
                                                f"умения като {tool}."))
                    self._log(f"✓ Поправих: думата „{word}“ вече показва уменията за {tool}.")
                    return

        # b) A new description for the skill and c) a lesson. When the model calls no skill at all (it
        # “invents” the password, translates by itself), a description rarely helps — the lesson is tried first.
        what = "; ".join(sorted({r.problem for r in results}))
        fix = dict(tool=tool, target=target, phrases=phrases, wrong=wrong, what=what,
                   regressions=regressions, routes=routes, path=path, module=module)
        no_tool = all(r.problem in ("не извика умение", "отговори, че не е успял") for r in results)
        attempts = (self._try_lesson, self._try_description) if no_tool else (self._try_description, self._try_lesson)
        for attempt in attempts:
            if attempt(fix, report):
                if routes:
                    router.learn(module, routes[module][0])
                self.host.refresh()
                return
        report.fixes.append(("неуспешна", f"„{target.phrase}“ ({tool}) — не намерих поправка, "
                                          f"която да минава всички тестове."))

    def _try_description(self, fix: dict, report: Report) -> bool:
        """A new description for the skill — only the text; the code stays the same."""
        tool, path, routes = fix["tool"], fix["path"], fix["routes"]
        old = registry._tools[tool]["schema"]["function"]["description"]
        others = "\n".join(f"Сбърка го с {w}: {registry._tools[w]['schema']['function']['description'][:200]}"
                           for w in sorted(fix["wrong"])[:2])
        for attempt in range(2):
            description = self._retrying(self._complete, DESCRIBE_PROMPT.format(
                phrases="\n".join(f"- „{p}“" for p in sorted(fix["phrases"])), what_happened=fix["what"], name=tool,
                description=old, others=others), 0.3 + 0.3 * attempt)
            description = description.strip().strip("„“\"' ")
            if not 20 <= len(description) <= 450 or "Args:" in description:
                continue
            code = path.read_text(encoding="utf-8")
            try:
                new_code = replace_description(code, tool, description)
            except (ValueError, SyntaxError):
                return False
            parsed = _parse_docstring(ast.get_docstring(next(
                n for n in ast.walk(ast.parse(new_code)) if isinstance(n, ast.FunctionDef) and n.name == tool)))[0]
            overrides = {tool: parsed}
            if not self._passes(fix["target"], 3, descriptions=overrides, routes=routes):
                continue
            if not all(self._passes(a, descriptions=overrides, routes=routes) for a in fix["regressions"]):
                continue
            self._wait_idle()
            with self.host.work_lock:
                if path.read_text(encoding="utf-8") != code:  # changed in the meantime — next time
                    return False
                forge._archive(path, ".bak", code)
                path.write_text(new_code, encoding="utf-8")
                try:
                    registry.load_skill_file(path)
                except Exception:  # noqa: BLE001
                    path.write_text(code, encoding="utf-8")
                    registry.load_skill_file(path)
                    return False
            report.fixes.append(("сам", f"пренаписах описанието на {tool}, за да разбирам „{fix['target'].phrase}“ "
                                        f"(само текста — кодът е същият; връща се с „върни предишната версия на {tool}“)."))
            self._log(f"✓ Поправих: ново описание на {tool} — „{parsed[:160]}“")
            return True
        return False

    def _try_lesson(self, fix: dict, report: Report) -> bool:
        """A lesson — a rule added to Orion's instructions (like the lessons from sir's
        remarks). At most MAX_TEST_LESSONS from test mode, so they do not push out sir's lessons."""
        tool = fix["tool"]
        if sum(1 for item in lessons.all() if item.get("source") == "тест") >= MAX_TEST_LESSONS:
            return False
        description = registry._tools[tool]["schema"]["function"]["description"][:300]
        reply = self._retrying(self._complete, LESSON_PROMPT.format(
            tool=tool, phrase=fix["target"].phrase, what=fix["what"], description=description), 0.3)
        lesson = (reply.strip().splitlines() or [""])[0].strip().strip("„“\"' ")
        if not 15 <= len(lesson) <= 250 or tool not in lesson:
            lesson = f"Когато сър поиска нещо като „{fix['target'].phrase}“, използвай умението {tool}, не отговаряй сам."
        if not self._passes(fix["target"], 3, lesson=lesson, routes=fix["routes"]):
            return False
        if not all(self._passes(a, lesson=lesson, routes=fix["routes"]) for a in fix["regressions"]):
            return False
        lessons.add(lesson, source="тест")
        report.fixes.append(("сам", f"научих поука, за да разбирам „{fix['target'].phrase}“: {lesson} "
                                    f"(маха се с „забрави поука номер …“)."))
        self._log(f"✓ Поправих: нова поука — „{lesson}“")
        return True

    def _keyword(self, phrase: str, tool: str, module: str) -> str | None:
        """One word from the request that will show the skill group from now on (e.g. „засечи“)."""
        group = [n for n, t in registry._tools.items() if t["module"] == module][:8]
        word = self._retrying(self._complete, KEYWORD_PROMPT.format(phrase=phrase, tools=", ".join(group)), 0.0)
        word = re.sub(r"[^\w-]", "", word.split()[0] if word.split() else "").lower()
        stem = word[:max(4, len(word) - 2)] if len(word) > 5 else word  # „засечи“ -> „засе“ also matches „засечете“
        others = [a.phrase.lower() for a in ASKS if a.expect and registry._tools.get(a.expect[0], {}).get("module") != module]
        if (len(stem) < 4 or stem not in phrase.lower() or word in STOP_WORDS or stem in STOP_WORDS
                or sum(stem in o for o in others) > 1):
            return None
        return stem

    def _fix_code(self, tool: str, failures: list[tuple[SkillCase, str]], report: Report, store: dict) -> None:
        path = registry.source_file(tool)
        if not path or path.name in forge.PROTECTED:
            return
        old_code = path.read_text(encoding="utf-8")
        own = {n for n in registry.names() if registry.source_file(n) == path}
        problems, _, _ = validate_skill_code(old_code, set(registry.names()) - own)
        case, problem = failures[0]
        if problems:  # a core file (ctypes, winreg…) — the model may not write it
            report.fixes.append(("ядро", f"{tool}: {problem[:160]} — файлът {path.name} използва системни модули "
                                         f"и не го пренаписвам сам."))
            return
        self._progress(f"fixing the code · {tool}")
        self._hud("thought", f"Умението {tool} е счупено — пиша нова версия и я проверявам в пясъчник.")
        cases = [c for c in self._skill_cases(store) if c.tool in own]
        error = next((e for e in reversed(registry.errors) if e["tool"] == tool), None)
        task = FIX_TASK.format(
            tool=tool, args=json.dumps(case.args, ensure_ascii=False), problem=problem,
            trace=f"Traceback:\n{error['traceback']}\n" if error else "",
            cases="\n".join(f"- {c.tool}({json.dumps(c.args, ensure_ascii=False)})"
                            + (f" -> резултатът трябва да съдържа {c.expect}" if c.expect else "") for c in cases),
            file=path.name, code=old_code)
        for attempt in range(2):
            code, warnings, tools, tries = self._write_code(task, own, old_code)
            if code is None:
                break
            failed = self._verify_code(path, code, cases)
            if not failed:
                proposal = Proposal("improve", f"Поправка от тест режима · {path.stem}",
                                    f"Тест режимът откри: {tool} — {problem[:200]}. Новата версия е проверена в "
                                    f"пясъчник: минават всички проверки на файла ({len(cases)}).",
                                    path, code, old_code, warnings, tools, tries)
                self._propose(proposal, tool, cases, report)
                return
            task += ("\n\nТвоята версия не мина проверката в пясъчника:\n"
                     + "\n".join(f"- {c.tool}: {p[:300]}" for c, p in failed[:4])
                     + "\nПоправи я и върни ЦЕЛИЯ файл в един ```python блок.")
        report.fixes.append(("неуспешна", f"{tool}: {problem[:160]} — не успях да напиша версия, която минава "
                                          f"проверките."))

    def _write_code(self, task: str, own: set[str], old_code: str):
        """As in the skill forge (self_improve.py), but the request is cancelled if sir starts talking."""
        taken = set(registry.names()) - own
        prompt = task
        for attempt in range(1, forge.MAX_ATTEMPTS + 1):
            reply = self._retrying(self._complete, prompt, 0.2, config.LLM_REASONING_EFFORT, CODER_PROMPT)
            code = extract_code(reply)
            problems, warnings, tools = validate_skill_code(code, taken)
            if _normalized(code) == _normalized(old_code):
                problems.insert(0, "Кодът е същият като досегашния — нищо не е поправено.")
            if not problems:
                return code, warnings, tools, attempt
            prompt = (f"{task}\n\nПредишният ти опит не мина проверката:\n- " + "\n- ".join(problems)
                      + "\nПоправи и върни ЦЕЛИЯ файл в един ```python блок.")
        return None, [], [], forge.MAX_ATTEMPTS

    def _verify_code(self, path: Path, code: str, cases: list[SkillCase]) -> list[tuple[SkillCase, str]]:
        """Loads the new code as a separate, temporary module (the real skill is untouched) and runs
        all the file's checks in the sandbox. Returns the failed ones."""
        temp = path.with_name(f"_selftest_{path.stem}.py")  # “_” — not loaded as a skill
        name = f"skills._selftest_{path.stem}"
        tools = OrionTools()
        self._wait_idle()
        with self.host.work_lock:
            import orion
            import orion.tools
            saved = orion.orion_tool, orion.tools.orion_tool
            try:
                temp.write_text(code, encoding="utf-8")
                orion.orion_tool = orion.tools.orion_tool = tools.tool
                spec = importlib.util.spec_from_file_location(name, temp)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
            except BaseException as e:  # noqa: BLE001 — the code does not load
                return [(cases[0] if cases else SkillCase("?"), f"не се зарежда: {type(e).__name__}: {e}")]
            finally:
                orion.orion_tool, orion.tools.orion_tool = saved
                temp.unlink(missing_ok=True)
            try:
                failed = []
                with Sandbox():
                    for i, case in enumerate(cases):
                        problem = self._run_skill_case(case, f"test:fix:{i}", tools)
                        if problem:
                            failed.append((case, problem))
                return failed
            finally:
                sys.modules.pop(name, None)

    def _propose(self, proposal: Proposal, tool: str, cases: list[SkillCase], report: Report) -> None:
        """The code is only enabled with sir's “Approve and enable”. Then — one more check."""
        self._wait_idle()
        with self.host.work_lock:
            approved = self.host.approve_test_fix(proposal)
            if not approved:
                report.fixes.append(("отказана", f"{tool}: поправката не беше одобрена — ще я предложа пак "
                                                 f"при следваща проверка."))
                return
            forge._activate(proposal)
            with Sandbox():
                failed = [c for i, c in enumerate(cases) if self._run_skill_case(c, f"test:after:{i}")]
            if failed:
                forge.undo(tool)
                report.fixes.append(("неуспешна", f"{tool}: след включването проверката не мина — върнах "
                                                  f"предишната версия."))
                return
        report.fixes.append(("одобрена", f"{tool}: поправен код, одобрен от сър; всички проверки минават."))
        self._log(f"✓ Поправката на {tool} е включена.")
        self.host.refresh()

    # --- End of the round ---------------------------------------------------------------------
    def _untested(self, store: dict) -> list[str]:
        covered = {c.tool for c in self._skill_cases(store)}
        return [n for n in registry.names() if n not in covered]

    def _finish(self, report: Report) -> None:
        self.last_report = report
        try:
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(report.markdown(), encoding="utf-8")
        except OSError as e:
            print(f"[Тест] Докладът не се записа: {e}")
        summary = report.summary()
        self._log(f"Кръг {report.number}: {summary} Пълният доклад: logs/self_test.md")
        if self.enabled:
            nxt = datetime.now() + timedelta(seconds=ROUND_PAUSE)
            self._progress(f"next check at {nxt:%H:%M}")
        # Out loud: the first round and any round with something new for sir.
        news = report.count("сам", "одобрена", "неуспешна", "ядро") or report.skill_failures
        if not report.stopped and (report.number == 1 or news):
            self.host.say(f"Самопроверката приключи, сър: {summary[0].lower() + summary[1:]}")

    def summary(self) -> str:
        """For „как мина теста“ (how did the test go)."""
        if not self.last_report:
            if self.running:
                return "Самопроверката още тече, сър. Ще Ви кажа резултата, когато приключи."
            return "Още не съм правил самопроверка, сър. Кажете „включи тест режим“."
        r = self.last_report
        text = f"При последната самопроверка {r.summary()}"
        if r.ask_failures:
            text += f" Например не разбрах „{r.ask_failures[0].ask.phrase}“."
        return text

    # --- The requests Orion invented itself ---------------------------------------------------
    @staticmethod
    def _load_store() -> dict:
        try:
            data = json.loads(STORE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return {"asks": data.get("asks", []), "skills": data.get("skills", []), "no_case": data.get("no_case", [])}

    @staticmethod
    def _save_store(store: dict) -> None:
        asks = store["asks"]
        if len(asks) > STORE_LIMIT:  # the oldest ones that always passed are dropped
            steady = [a for a in asks if a.get("failed", 0) == 0 and a.get("passed", 0) >= 2]
            drop = {id(a) for a in steady[:len(asks) - STORE_LIMIT]}
            store["asks"] = [a for a in asks if id(a) not in drop]
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
