"""
Тест режим — Орион сам се проверява, намира грешките си и ги поправя.

Един кръг:
  1. Умения. Всяко умение от jarvis/self_test_cases.py се пуска с примерни данни в пясъчник:
     бележките, напомнянията, известията и портфейлът са временни копия, нищо не се отваря на
     екрана, клипбордът се връща, всяко потвърждение (писмо, изтриване) се отказва. Опасните
     умения (изключване, писма, звук, изтриване…) изобщо не се пускат.
  2. Разбиране. Молби — готови и нови, които Орион сам измисля за уменията си — минават по
     същия път като истинските (рефлекси -> езиков модел). Проверява се дали е избрал правилното
     умение. Действията не се изпълняват: вместо тях има манекен, който само ги отбелязва.
  3. Поправки.
     - Неразбрана молба: Орион сам добавя ключова дума към подбора на умения (jarvis/router.py)
       или пренаписва описанието на умението — само текста, кодът гарантирано остава същият.
       Промяната остава само ако молбата вече се разбира и старите тестове още минават.
     - Счупено умение: Орион пише нов код, проверява го в пясъчника с всички тестове на файла и
       го показва за одобрение. Кодът се изпълнява с пълен достъп до компютъра, затова последната
       дума е на сър — както при всеки код, който Орион пише.
  4. Доклад — в журнала, в logs/self_test.md и на глас.

Орион не пречи на сър: тестовете вървят само когато той мълчи. Ако заговори, текущата заявка
към модела се прекъсва и тестът продължава по-късно.
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

from . import google, reflexes, router
from .brain import HONEST_FAILURE, READ_ONLY_TOOLS, Brain
from .memory import ConversationMemory
from .reminders import book as reminder_book
from .self_improve import CODER_PROMPT, Proposal, _normalized, extract_code, forge, lessons, validate_skill_code
from .self_test_cases import ASKS, SKILL_CASES, Ask, SkillCase
from .tools import JarvisTools, _parse_docstring, registry

MEMORY_DIR = config.BASE_DIR / "memory"
STORE = MEMORY_DIR / "self_tests.json"            # молбите и проверките, които Орион е измислил сам
REPORT = config.BASE_DIR / "logs" / "self_test.md"
BOX = Path(tempfile.gettempdir()) / "mitko_selftest"

ROUND_PAUSE = 10 * 60   # секунди между кръговете, докато тест режимът е включен
SKILLS_EVERY = 3        # уменията (мрежа, файлове) — на всеки 3 кръга; разбирането — всеки кръг
NEW_ASKS = 8            # за колко умения Орион измисля нови молби на кръг
MAX_FIXES = 4           # поправки на кръг — останалите остават за следващия
IDLE_SECONDS = 20       # толкова след последната молба на сър тестовете още чакат
STORE_LIMIT = 150
MAX_RETRIES = 3         # колко пъти един тест може да бъде прекъснат, преди да се пропусне
MAX_TEST_LESSONS = 10   # поуки от тест режима (общо са до 40 — останалите са за забележките на сър)

# Пясъчникът подменя файлове на цялата програма. Докато е активен, напомнянията и известията
# за цени чакат (виж app.py -> _reminder_loop), за да не четат или запишат тестовите копия.
sandbox_lock = threading.Lock()

# При проверката на разбирането тези умения работят наистина — само четат и не пазят нищо.
# Всички останали се заменят с манекен, който само отбелязва извикването.
LIVE_TOOLS = {
    "get_current_time", "calculate", "get_weather", "days_until_date", "wikipedia", "convert_currency",
    "convert_units", "search_web", "read_webpage", "market_price", "market_overview", "crypto_market",
    "compare_assets", "top_stock_movers", "crypto_fear_greed", "convert_crypto", "weather_week",
    "weather_hourly", "will_it_rain", "air_quality", "uv_index", "date_after_days", "days_between",
    "weekday_of_date", "age_from_birthday", "sunrise_sunset", "moon_phase", "bulgarian_holidays",
    "next_holiday", "name_day", "todays_name_days", "random_number", "flip_coin",  # паролата се копира -> манекен
    "roll_dice", "pick_random", "count_text", "encode_base64", "decode_base64", "hash_text",
    "convert_number_base", "roman_numeral", "convert_timestamp", "number_stats", "percent_change",
    "split_bill", "loan_payment", "compound_interest", "vat_calculator", "discount_price", "savings_goal",
    "fuel_cost", "bmi_calculator", "translate_text", "detect_language", "define_word", "country_info",
    "distance_between", "my_public_ip", "ping_host", "website_status", "local_network_info", "wifi_info",
    "port_in_use", "dns_lookup", "system_status", "resource_hogs", "running_programs", "windows_version",
    "list_skills", "list_lessons", "radio_stations",
}
STUB = "Изпълнено успешно."
# За тях Орион не измисля молби: самоусъвършенстването се проверява отделно, а не чрез себе си.
NOT_ASKED = {"learn_lesson", "forget_lesson", "create_skill", "improve_skill", "undo_skill_change",
             "recent_errors", "list_lessons", "remember"}
# Мрежови проблеми не са бъг в кода — умението се проверява пак, но не се „поправя“.
NETWORK_RE = re.compile(
    r"URLError|timed out|TimeoutError|ConnectionError|Connection(Reset|Refused|Aborted)|getaddrinfo|"
    r"RemoteDisconnected|HTTP Error (5\d\d|429)|SSLError|IncompleteRead|No route to host|"
    r"temporarily unavailable|Max retries|ReadTimeout|не отговори за", re.IGNORECASE)
# Думи, които са във всякакви молби — не стават за ключова дума на група умения.
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
    """Сър изключи тест режима."""


class Interrupted(Exception):
    """Сър заговори — текущият тест се прекъсва и се пуска пак по-късно."""


class StoppableClient:
    """OpenAI клиент за тест режима. Отговорът идва на части (stream) и между всеки две части
    се проверява дали сър не е заговорил — тогава потокът се затваря, Ollama спира да генерира
    и отговорът на сър не чака теста. Връща същия вид отговор като обикновения клиент
    (content, tool_calls, reasoning), за да може и Brain да го ползва."""

    def __init__(self, check: "Callable[[], type[Exception] | None]"):
        self._client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, timeout=240, max_retries=0)
        self._check = check  # None — продължи; Interrupted/Stopped — спри
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _stop_if_needed(self) -> None:
        reason = self._check()
        if reason:
            raise reason()

    def _create(self, **kwargs):
        self._stop_if_needed()
        stream = self._client.chat.completions.create(stream=True, **kwargs)
        content, reasoning, calls = [], [], []
        try:
            for chunk in stream:
                self._stop_if_needed()
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content.append(delta.content)
                extra = delta.model_extra or {}
                if extra.get("reasoning"):
                    reasoning.append(extra["reasoning"])
                for call in delta.tool_calls or []:
                    same = [c for c in calls if call.index is not None and c["index"] == call.index]
                    slot = same[0] if same else {"index": call.index, "id": None, "name": "", "arguments": ""}
                    if not same:
                        calls.append(slot)
                    slot["id"] = call.id or slot["id"]
                    if call.function:
                        slot["name"] += call.function.name or ""
                        slot["arguments"] += call.function.arguments or ""
        finally:
            stream.close()
        tool_calls = [SimpleNamespace(id=c["id"] or f"call_{i}", type="function",
                                      function=SimpleNamespace(name=c["name"], arguments=c["arguments"] or "{}"))
                      for i, c in enumerate(calls)]
        message = SimpleNamespace(content="".join(content), tool_calls=tool_calls or None,
                                  model_extra={"reasoning": "".join(reasoning)} if reasoning else {})
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _json_in(text: str, opener: str):
    """Първият JSON масив/обект в отговора на модела (или None)."""
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
#  Пясъчник
# =====================================================================================
class Sandbox:
    """Докато е активен, уменията пипат само временни копия: файловете с данни от memory/ са
    в BOX, нищо не се отваря на екрана, запомнените списъци и клипбордът се връщат след това,
    а всяко потвърждение (писмо, изтриване) се отказва."""

    SKIP = {"jarvis.self_test", "jarvis.router", "jarvis.self_improve"}

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
        # Отварянето на файлове и сайтове се спира навсякъде — и там, където модулът си го е
        # запазил под друго име (напр. `open_path = os.startfile`).
        openers = {id(f) for f in (getattr(os, "startfile", None), webbrowser.open, webbrowser.open_new,
                                   webbrowser.open_new_tab) if f}
        for name, module in list(sys.modules.items()):
            if module is None or name in self.SKIP or not name.startswith(("skills.", "jarvis.")):
                continue
            for attr, value in list(vars(module).items()):
                if attr.startswith("__"):
                    continue
                if id(value) in openers:
                    self._set(module, attr, lambda *args, **kwargs: None)
                elif isinstance(value, Path) and value.suffix == ".json" and MEMORY_DIR in value.parents:
                    self._set(module, attr, BOX / value.name)
                elif name.startswith("skills.") or name == "jarvis.folders":
                    if attr.startswith(("last_", "_last")):  # „последният списък с файлове/писма…“
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
        except Exception:  # noqa: BLE001 — без клипборд тестът пак върви
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


# Умение, което прави нещо навън (писмо, изтриване, отваряне…), не се пуска с измислени данни.
ACTION_WORDS = re.compile(
    r"изпра|прати|праща|пише на|трие|изтри|премахва|маха|купува|плаща|публикува|качва|изключва|рестарт|"
    r"затваря|отваря|пуска|стартира|печат|принт|запис|създава|добавя|сменя|променя|"
    r"send|post|delete|upload|print|write|open", re.IGNORECASE)


def _may_invent(name: str) -> bool:
    """Може ли Орион сам да измисли и пусне проверка на умението: само ако го е написал сам
    (готовите умения имат ръчни проверки в self_test_cases.py) и то само чете — без запис на
    файлове, програми, изпращане на данни и думи за действие в описанието."""
    path = registry.source_file(name)
    if name in NOT_ASKED or name not in registry.names() or not path or not path.exists():
        return False
    if not any(forge.history_dir.glob(f"{path.stem}__*.created")):  # не е писано от Орион
        return False
    code = path.read_text(encoding="utf-8")
    problems, warnings, _ = validate_skill_code(code, set())
    if problems or set(warnings) - {"достъп до интернет"}:
        return False
    if re.search(r"startfile|\b(?:data|method)\s*=|urlopen\([^)]*,\s*[^t)]", code):  # отваряне, изпращане на данни
        return False
    return not ACTION_WORDS.search(registry._tools[name]["schema"]["function"]["description"])


def _call(tools, name: str, args: dict, timeout: float = 60.0) -> str:
    """Умението в отделна нишка — ако увисне, тестът продължава (и отбелязва грешката)."""
    box: dict[str, str] = {}
    worker = threading.Thread(target=lambda: box.update(result=tools.call(name, args)), daemon=True,
                              name=f"selftest-{name}")
    worker.start()
    worker.join(timeout)
    return box.get("result", f"Грешка при изпълнение на '{name}': TimeoutError: не отговори за {timeout:.0f} секунди")


def _problem(case: SkillCase, result: str) -> str | None:
    """Какво не е наред с резултата (или None)."""
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
#  Регистърът, който вижда тестовият „мозък“
# =====================================================================================
class TestTools:
    """Истински са само LIVE_TOOLS, останалите умения са манекени. По желание — други описания
    на уменията, за да се провери поправка на описание, преди да се запише."""

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
#  Поправка на описание: само текстът на docstring-а, кодът остава същият
# =====================================================================================
def _shape(code: str) -> str:
    """Кодът без docstring-ите — за доказателство, че е променен само текстът."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:]
    return ast.dump(tree)


def replace_description(code: str, func: str, description: str) -> str:
    """Същият файл, но с ново описание на умението `func` (секцията „Args:“ остава)."""
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
    if _shape(new_code) != _shape(code):  # не бива да се случи — но ако се случи, нищо не се записва
        raise ValueError("промяната засяга не само описанието")
    return new_code


# =====================================================================================
#  Доклад
# =====================================================================================
@dataclass
class Report:
    number: int
    started: datetime = field(default_factory=datetime.now)
    skills_total: int = 0
    skills_ok: int = 0
    skill_failures: list[tuple[SkillCase, str, bool]] = field(default_factory=list)  # (тест, проблем, мрежа)
    asks_total: int = 0
    asks_ok: int = 0
    ask_failures: list[AskResult] = field(default_factory=list)
    new_asks: int = 0
    fixes: list[tuple[str, str]] = field(default_factory=list)  # („сам“/„одобрена“/…, описание)
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
#  Тест режимът
# =====================================================================================
class SelfTester:
    """`host` е приложението (app.py -> Jarvis): brain, work_lock, hud(), say(), test_idle(),
    approve_test_fix(). work_lock е ключалката, която държи и worker-ът, докато отговаря на сър:
    така тест в пясъчника и истинска молба никога не вървят едновременно."""

    def __init__(self, host):
        self.host = host
        self.enabled = False
        self.thread: threading.Thread | None = None
        self.client = StoppableClient(self._stop_reason)
        self.last_report: Report | None = None
        self.rounds = 0

    # --- Включване ---------------------------------------------------------------------------
    def start(self) -> bool:
        """Включва тест режима. False — ако вече работи."""
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

    # --- Връзка с прозореца ------------------------------------------------------------------
    def _hud(self, fn: str, *args) -> None:
        try:
            self.host.hud(fn, *args)
        except Exception:  # noqa: BLE001 — прозорецът може да се затваря
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

    # --- Изчакване на сър ---------------------------------------------------------------------
    def _wait_idle(self) -> None:
        """Чака, докато сър не говори и Орион не работи. Stopped — ако тест режимът е изключен."""
        while self.enabled and not self.host.test_idle():
            time.sleep(0.5)
        if not self.enabled:
            raise Stopped()

    def _stop_reason(self) -> type[Exception] | None:
        """За StoppableClient: спира заявката, ако сър е заговорил или е изключил тест режима."""
        if not self.enabled:
            return Stopped
        return None if self.host.test_idle() else Interrupted

    def _retrying(self, action, *args):
        """Изпълнява `action`; ако сър го прекъсне — изчаква тишина и опитва пак."""
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

    # --- Главният цикъл -----------------------------------------------------------------------
    def _loop(self) -> None:
        while self.enabled:
            self.rounds += 1
            report = Report(self.rounds)
            try:
                self._round(report)
            except Stopped:
                report.stopped = True
            except Exception as e:  # noqa: BLE001 — грешка в самия тест не бива да спира Орион
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

    # --- 1. Умения ----------------------------------------------------------------------------
    def _skill_cases(self, store: dict) -> list[SkillCase]:
        names = set(registry.names())
        cases = [c for c in SKILL_CASES if c.tool in names and (c.needs != "google" or google.is_connected())]
        cases += [SkillCase(s["tool"], s["args"]) for s in store["skills"] if s["tool"] in names and _may_invent(s["tool"])]
        return cases

    def _check_skills(self, report: Report, store: dict) -> None:
        self._invent_skill_cases(store)
        cases = self._skill_cases(store)
        # По модули: тестовете на един файл вървят заедно в един пясъчник (запис -> четене).
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
                    self._progress(f"умения {done}/{len(cases)}")
                    problem = self._run_skill_case(case, f"test:{done}")
                    if problem:
                        failed.append((case, problem))
        # Мрежата понякога се бави — неуспелите се проверяват още веднъж.
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
        except Exception as e:  # noqa: BLE001 — счупена подготовка = неуспешен тест
            result = f"Грешка при подготовката: {type(e).__name__}: {e}"
        problem = _problem(case, result)
        self._task_done(key, "работи" if problem is None else problem, problem is None)
        return problem

    def _invent_skill_cases(self, store: dict) -> None:
        """Новите умения, които Орион е написал сам, нямат готова проверка — той измисля данни
        за тест. Само ако умението само чете (виж _may_invent): иначе би изпратило, изтрило или
        отворило нещо наистина."""
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

    # --- 2. Разбиране -------------------------------------------------------------------------
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
            self._progress(f"разбиране {i}/{len(asks)}")
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
        """Молбата минава по пътя на истинските: рефлекс -> модел. Действията са манекени.
        descriptions/routes/lesson — поправка за проба, преди да се запише."""
        tools = TestTools(descriptions)
        reflex = reflexes.respond(ask.phrase)
        if reflex and reflex.tool:
            result = tools.call(reflex.tool, reflex.arguments_json)
            return _evaluate(ask, tools.calls, reflex.answer or result, "рефлекс")
        if reflex and not reflex.action:  # час, дата, ден
            return _evaluate(ask, ["get_current_time"], reflex.answer, "рефлекс")
        if reflex:
            return _evaluate(ask, [], f"({reflex.action})", "рефлекс")
        answer = self._test_brain(tools, routes, lesson).think(ask.phrase)  # Interrupted, ако сър заговори
        return _evaluate(ask, tools.calls, answer, "модел")

    def _test_brain(self, tools: TestTools, routes: dict | None, lesson: str | None = None) -> Brain:
        source = self.host.brain
        def with_lesson() -> str:  # поуката за проба — след научените досега
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
        brain.route_extra = routes
        return brain

    def _second_opinion(self, result: AskResult, store: dict) -> AskResult:
        """Измислената молба е получила друго умение — може би и то е вярно („времето утре“
        -> get_weather вместо will_it_rain). Орион преценява; ако е вярно, го приема занапред."""
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
        """Орион сам измисля нови молби за уменията, които досега са били най-малко проверявани."""
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
            self._progress(f"пиша нови тестове {i}/{NEW_ASKS}")
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
                try:  # безсмислена молба („Заправи гласа на пълна сила“) би довела до безсмислена „поправка“
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

    # --- 3. Поправки --------------------------------------------------------------------------
    def _fix(self, report: Report, store: dict) -> None:
        budget = MAX_FIXES
        # Разбирането: по едно умение наведнъж (няколко неразбрани молби за едно умение — една поправка).
        by_tool: dict[str, list[AskResult]] = {}
        for result in report.ask_failures:
            if result.problem.startswith("грешен отговор") and set(result.used) & set(result.ask.expect):
                # Умението е правилното — сгрешен е самият отговор (напр. факт). Описание не помага.
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
        # Кодът на уменията.
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
        """Молбите, които една поправка може да засегне — трябва да продължат да минават."""
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
        self._progress(f"поправям · {tool}")
        self._hud("thought", f"Не разбрах „{results[0].ask.phrase}“ — търся защо и как да се поправя.")
        target, phrases = results[0].ask, {r.ask.phrase for r in results}
        wrong = {u for r in results for u in r.used if u in registry.names() and u != tool}
        # Сравнява се само с молбите, които в този кръг са минали.
        failing = {r.ask.phrase for r in report.ask_failures}
        regressions = self._regressions({tool, *wrong}, store, failing)

        # а) Групата на умението е била скрита за тази молба -> ключова дума за подбора.
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

        # б) Ново описание на умението и в) поука. Когато моделът изобщо не вика умение (сам
        # „измисля“ паролата, сам превежда), описанието рядко помага — първо се пробва поуката.
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
        """Ново описание на умението — само текстът, кодът остава същият."""
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
                if path.read_text(encoding="utf-8") != code:  # междувременно е променен — следващия път
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
        """Поука — правило, което се добавя към инструкциите на Орион (като поуките от забележките
        на сър). Най-много MAX_TEST_LESSONS от тест режима, за да не изтласкат поуките на сър."""
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
        """Една дума от молбата, която да показва групата умения занапред (напр. „засечи“)."""
        group = [n for n, t in registry._tools.items() if t["module"] == module][:8]
        word = self._retrying(self._complete, KEYWORD_PROMPT.format(phrase=phrase, tools=", ".join(group)), 0.0)
        word = re.sub(r"[^\w-]", "", word.split()[0] if word.split() else "").lower()
        stem = word[:max(4, len(word) - 2)] if len(word) > 5 else word  # „засечи“ -> „засе“ хваща и „засечете“
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
        if problems:  # файл от ядрото (ctypes, winreg…) — моделът няма право да го пише
            report.fixes.append(("ядро", f"{tool}: {problem[:160]} — файлът {path.name} използва системни модули "
                                         f"и не го пренаписвам сам."))
            return
        self._progress(f"поправям кода · {tool}")
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
        """Като в работилницата за умения (self_improve.py), но заявката се прекъсва, ако сър заговори."""
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
        """Зарежда новия код като отделен, временен модул (истинското умение не се пипа) и пуска
        всички проверки на файла в пясъчника. Връща неуспелите."""
        temp = path.with_name(f"_selftest_{path.stem}.py")  # „_“ — не се зарежда като умение
        name = f"skills._selftest_{path.stem}"
        tools = JarvisTools()
        self._wait_idle()
        with self.host.work_lock:
            import jarvis
            import jarvis.tools
            saved = jarvis.jarvis_tool, jarvis.tools.jarvis_tool
            try:
                temp.write_text(code, encoding="utf-8")
                jarvis.jarvis_tool = jarvis.tools.jarvis_tool = tools.tool
                spec = importlib.util.spec_from_file_location(name, temp)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
            except BaseException as e:  # noqa: BLE001 — кодът не се зарежда
                return [(cases[0] if cases else SkillCase("?"), f"не се зарежда: {type(e).__name__}: {e}")]
            finally:
                jarvis.jarvis_tool, jarvis.tools.jarvis_tool = saved
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
        """Кодът се включва само с „Одобри и включи“ от сър. После — още една проверка."""
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

    # --- Край на кръга ------------------------------------------------------------------------
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
            self._progress(f"следваща проверка в {nxt:%H:%M}")
        # На глас: първият кръг и всеки, в който има нещо ново за сър.
        news = report.count("сам", "одобрена", "неуспешна", "ядро") or report.skill_failures
        if not report.stopped and (report.number == 1 or news):
            self.host.say(f"Самопроверката приключи, сър: {summary[0].lower() + summary[1:]}")

    def summary(self) -> str:
        """За „как мина теста“."""
        if not self.last_report:
            if self.running:
                return "Самопроверката още тече, сър. Ще Ви кажа резултата, когато приключи."
            return "Още не съм правил самопроверка, сър. Кажете „включи тест режим“."
        r = self.last_report
        text = f"При последната самопроверка {r.summary()}"
        if r.ask_failures:
            text += f" Например не разбрах „{r.ask_failures[0].ask.phrase}“."
        return text

    # --- Молбите, които Орион е измислил сам ---------------------------------------------------
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
        if len(asks) > STORE_LIMIT:  # отпадат най-старите, които винаги са минавали
            steady = [a for a in asks if a.get("failed", 0) == 0 and a.get("passed", 0) >= 2]
            drop = {id(a) for a in steady[:len(asks) - STORE_LIMIT]}
            store["asks"] = [a for a in asks if id(a) not in drop]
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
