"""
Orion's self-improvement.

1. Lessons (LessonBook) — when sir corrects Orion, the lesson is saved in memory/lessons.json
   and added to the persona in every conversation. So the mistake is not repeated.

2. The skill forge (SkillForge) — Orion writes new skills and fixes existing ones by itself:
       writes code -> checks it -> on a problem reads the error and tries again (up to 3 times)
       -> shows the code to sir for approval -> archives the old version -> loads the new one without a restart.
   Every change can be reverted with undo().

Why approval is required: code written by the model runs with full access to the computer.
The checks below catch errors and dangerous constructs, but a human has the final say.
"""
import ast
import difflib
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import config

from .tools import OrionTools, registry


# =====================================================================================
#  Lessons
# =====================================================================================
class LessonBook:
    def __init__(self, path: Path, limit: int = 40):
        self.path = Path(path)
        self.limit = limit
        self._lock = threading.Lock()

    def all(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _save(self, lessons: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(lessons, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, text: str, source: str = "") -> int:
        """`source` — „тест“ for lessons from test mode (orion/self_test.py)."""
        text = text.strip()
        with self._lock:
            lessons = self.all()
            if text and all(l["text"].lower() != text.lower() for l in lessons):
                lessons.append({"text": text, "date": f"{datetime.now():%d.%m.%Y %H:%M}",
                                **({"source": source} if source else {})})
                self._save(lessons[-self.limit:])  # The oldest drop off when full.
            return len(lessons)

    def remove(self, number: int) -> str | None:
        with self._lock:
            lessons = self.all()
            if not 1 <= number <= len(lessons):
                return None
            removed = lessons.pop(number - 1)
            self._save(lessons)
            return removed["text"]

    def as_prompt(self) -> str:
        lessons = self.all()
        if not lessons:
            return ""
        rules = "\n".join(f"{i}. {l['text']}" for i, l in enumerate(lessons, 1))
        return f"Поуки от минали грешки — спазвай ги винаги, те са по-важни от примерите:\n{rules}"


# =====================================================================================
#  Code check (static — nothing is executed)
# =====================================================================================
ALLOWED_PARAM_TYPES = {"str", "int", "float", "bool"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "globals", "locals", "breakpoint"}
FORBIDDEN_MODULES = {"importlib", "ctypes", "winreg", "pickle", "marshal"}
# REAL TRADE trades real money by itself — code Orion writes may not reach the trading package at all.
TRADING_BAN = "Търговията (orion.trading) е забранена за умения, които пиша сам — там се търгува с истински пари."
# Safe calls allowed at the top level (e.g. PATTERN = re.compile(...)).
SAFE_TOPLEVEL_CALLS = {"Path", "dict", "list", "set", "tuple", "frozenset", "range", "compile", "join"}
RISKY = {
    "subprocess": "стартира програми/команди",
    "shutil": "копира или трие файлове",
    "os.remove": "трие файлове", "os.unlink": "трие файлове", "os.rmdir": "трие папки",
    "os.system": "изпълнява команди", "socket": "мрежови връзки",
    "urllib": "достъп до интернет", "webbrowser": "отваря браузъра",
}


def _call_name(node: ast.Call) -> str:
    func = node.func
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def _is_tool_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return isinstance(target, ast.Name) and target.id == "orion_tool"


def validate_skill_code(code: str, taken_names: set[str]) -> tuple[list[str], list[str], list[str]]:
    """Returns (problems, warnings, skill names). Problems block the code."""
    problems, warnings = [], []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Синтактична грешка на ред {e.lineno}: {e.msg}"], [], []

    imports_tool = False
    tools = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue  # docstring
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in modules:
                if m.split(".")[0] in FORBIDDEN_MODULES:
                    problems.append(f"Модулът „{m}“ е забранен.")
            if isinstance(node, ast.ImportFrom) and node.module == "orion" and any(a.name == "orion_tool" for a in node.names):
                imports_tool = True
            continue
        if isinstance(node, ast.FunctionDef):
            for default in node.args.defaults + [d for d in node.args.kw_defaults if d]:
                if any(isinstance(n, ast.Call) for n in ast.walk(default)):
                    problems.append(f"„{node.name}“: стойностите по подразбиране не трябва да викат функции.")
            if any(_is_tool_decorator(d) for d in node.decorator_list):
                tools.append(node)
            elif node.decorator_list:
                problems.append(f"„{node.name}“: разрешен е само декораторът @orion_tool.")
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            for n in ast.walk(value) if value else []:
                if isinstance(n, ast.Call) and _call_name(n).split(".")[-1] not in SAFE_TOPLEVEL_CALLS:
                    problems.append(f"Ред {node.lineno}: на най-горно ниво не се викат функции "
                                    f"(„{_call_name(n)}“ ще се изпълни при зареждане) — премести го във функция.")
            continue
        problems.append(f"Ред {node.lineno}: на най-горно ниво са разрешени само import-и, функции и константи.")

    if not imports_tool:
        problems.append("Липсва „from orion import orion_tool“.")
    if not tools:
        problems.append("Няма нито една функция с @orion_tool.")

    for fn in tools:
        if not ast.get_docstring(fn):
            problems.append(f"„{fn.name}“ няма docstring — без него Орион не знае кога да го ползва.")
        for arg in fn.args.args:
            ann = arg.annotation
            if not (isinstance(ann, ast.Name) and ann.id in ALLOWED_PARAM_TYPES):
                problems.append(f"„{fn.name}“: параметърът „{arg.arg}“ трябва да е str, int, float или bool.")
        if fn.name in taken_names:
            problems.append(f"Вече има друго умение с име „{fn.name}“ — избери друго име.")

    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name = _call_name(n)
            if name.split(".")[-1] in FORBIDDEN_CALLS and "." not in name:
                problems.append(f"„{name}()“ е забранено.")
            if name == "open" and any(isinstance(a, ast.Constant) and isinstance(a.value, str) and set(a.value) & set("wax")
                                      for a in n.args[1:2] + [k.value for k in n.keywords if k.arg == "mode"]):
                warnings.append("записва във файлове")
    used = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    used |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    used |= {_call_name(n) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for key, meaning in RISKY.items():
        if any(u == key or u.startswith(key + ".") for u in used):
            warnings.append(meaning)

    if _reaches_trading(tree):
        problems.append(TRADING_BAN)
    problems += _undefined_names(code)
    return list(dict.fromkeys(problems)), sorted(set(warnings)), [fn.name for fn in tools]


def _skill_reaches_trading(name: str, depth: int) -> bool:
    """skills/<name>.py imports orion.trading — code Orion writes may not reach trading through a skill module."""
    try:
        source = (config.SKILLS_DIR / f"{name}.py").read_text(encoding="utf-8")
        return _reaches_trading(ast.parse(source), depth + 1)
    except (OSError, SyntaxError, ValueError):
        return False


def _reaches_trading(tree: ast.AST, depth: int = 0) -> bool:
    """Any import of orion.trading (also inside functions), the attribute orion.trading, or a skills module that
    reaches it (followed two levels deep)."""
    def skill(name: str) -> bool:
        return depth < 2 and bool(name) and _skill_reaches_trading(name, depth)

    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                parts = a.name.split(".")
                if parts[:2] == ["orion", "trading"] or (parts[0] == "skills" and len(parts) > 1 and skill(parts[1])):
                    return True
        if isinstance(n, ast.ImportFrom) and n.module:
            parts = n.module.split(".")
            if parts[:2] == ["orion", "trading"] or (n.module == "orion" and any(a.name == "trading" for a in n.names)):
                return True
            if parts[0] == "skills" and (skill(parts[1]) if len(parts) > 1 else any(skill(a.name) for a in n.names)):
                return True
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            if (n.value.id == "orion" and n.attr == "trading") or (n.value.id == "skills" and skill(n.attr)):
                return True
    return False


def _undefined_names(code: str) -> list[str]:
    """Catches names that are used but not defined/imported (e.g. a deleted `import json`)."""
    try:
        import pyflakes.api
        import pyflakes.messages
    except ImportError:
        return []

    class Collector:
        def __init__(self):
            self.problems = []

        def unexpectedError(self, filename, message):  # noqa: N802 — the pyflakes interface
            pass

        def syntaxError(self, filename, message, line, offset, text):  # noqa: N802
            pass

        def flake(self, message):
            if isinstance(message, (pyflakes.messages.UndefinedName, pyflakes.messages.UndefinedLocal)):
                self.problems.append(f"Ред {message.lineno}: {message.message % message.message_args} "
                                     f"(липсва import или дефиниция).")

    collector = Collector()
    pyflakes.api.check(code, "skill.py", collector)
    return collector.problems


def _normalized(code: str) -> str:
    """Code without blank lines and trailing spaces — to compare whether anything changed."""
    return "\n".join(line.rstrip() for line in code.strip().splitlines() if line.strip())


def modernize(code: str) -> str:
    """Code from when the package was called “jarvis” -> “orion” (archived versions of
    skills, the model's habit)."""
    code = re.sub(r"^from jarvis import (.*)$",
                  lambda m: "from orion import " + m[1].replace("jarvis_tool", "orion_tool"), code, flags=re.MULTILINE)
    code = re.sub(r"^from jarvis\.", "from orion.", code, flags=re.MULTILINE)
    return code.replace("jarvis_tool", "orion_tool")


def extract_code(reply: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", reply, re.DOTALL)
    if blocks:
        return modernize(max(blocks, key=len).strip() + "\n")
    return modernize(reply.strip() + "\n")


# =====================================================================================
#  The skill forge
# =====================================================================================
CODER_PROMPT = '''Ти си внимателен Python програмист. Пишеш умения (плъгини) за гласовия асистент Орион.
Среда: Windows 11, Python 3.12. Отговаряш САМО с един ```python блок, който съдържа ЦЕЛИЯ файл.

Правила:
1. Файлът започва с кратък docstring и `from orion import orion_tool`.
2. Всяко умение е функция с декоратор @orion_tool. Параметрите имат type hints само str, int, float или bool.
   Функцията връща str.
3. Docstring на всяко умение (на български): първо изречение — КОГА Орион да го използва,
   после секция „Args:“ с по един ред за всеки параметър.
4. Връщай кратък текст на български с резултата — той се чете на глас. При проблем хвърли
   изключение с ясно съобщение (напр. raise ValueError("Не намерих града.")).
5. Само стандартната библиотека (urllib.request, json, datetime, math, re, os, pathlib, webbrowser,
   subprocess и т.н.). За интернет: urllib.request с timeout=10 и безплатни API без ключ.
6. На най-горно ниво — само import-и, функции и константи. Никакъв код, който се изпълнява при зареждане.
7. Никога не трий файлове, не променяй системни настройки и не изпращай лични данни.
8. Помощните функции започват с „_“ и нямат декоратор.
9. За пароли, кодове и всичко, свързано със сигурност, използвай модула secrets, не random.
10. Ако стойност може да варира (дължина, град, дата), направи я параметър, а не твърдо зададена.

Пример за добре написано умение:
```python
"""Курсове на валути."""
import json
import urllib.request

from orion import orion_tool


@orion_tool
def get_exchange_rate(currency: str) -> str:
    """Връща курса на валута спрямо евро, когато сър пита колко струва долар, паунд и т.н.

    Args:
        currency: Трибуквен код на валутата, напр. "USD".
    """
    code = currency.strip().upper()
    url = f"https://api.frankfurter.app/latest?from=EUR&to={code}"
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.load(response)
    rate = data["rates"].get(code)
    if rate is None:
        raise ValueError(f"Не познавам валутата {code}.")
    return f"Едно евро е {rate} {code}."
```'''


@dataclass
class Proposal:
    """A proposed change that sir approves or rejects."""
    kind: str                  # "create" | "improve"
    title: str
    reason: str
    file: Path
    code: str
    old_code: str | None = None
    warnings: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    attempts: int = 1

    @property
    def diff(self) -> str:
        if self.old_code is None:
            return ""
        return "".join(difflib.unified_diff(
            self.old_code.splitlines(keepends=True), self.code.splitlines(keepends=True),
            fromfile="сега", tofile="ново", n=2,
        ))


class ForgeError(RuntimeError):
    pass


class SkillForge:
    MAX_ATTEMPTS = 3
    # The self-improvement system itself cannot rewrite itself.
    PROTECTED = {"self_improvement.py"}

    def __init__(self, registry: OrionTools, skills_dir: Path):
        self.registry = registry
        self.skills_dir = Path(skills_dir)
        self.history_dir = self.skills_dir / ".history"
        self.client = None
        self.model = None
        self.reasoning_effort = None
        # Replaced by the app: a dialog with buttons / a question in the console.
        self.approve: Callable[[Proposal], bool] = lambda proposal: False
        self.progress: Callable[[str], None] = lambda message: print(f"[Самоусъвършенстване] {message}")

    def configure(self, client, model: str, reasoning_effort: str | None = None) -> None:
        self.client, self.model = client, model
        self.reasoning_effort = reasoning_effort  # for thinking models — how much to think about the code

    def thinking(self, effort: str | None) -> dict:
        """The thinking parameter — only if the model supports it (set in config)."""
        return {"reasoning_effort": effort} if self.reasoning_effort and effort else {}

    # --- Generation with automatic self-correction --------------------------------------
    def _write_code(self, task: str, own_names: set[str],
                    old_code: str | None = None) -> tuple[str, list[str], list[str], int]:
        if self.client is None:
            raise ForgeError("Езиковият модел още не е готов.")
        taken = set(self.registry.names()) - own_names
        messages = [{"role": "system", "content": CODER_PROMPT}, {"role": "user", "content": task}]
        problems: list[str] = []
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            self.progress(f"пиша код · опит {attempt}")
            reply = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0.2,
                **self.thinking(self.reasoning_effort),
            ).choices[0].message.content or ""
            code = extract_code(reply)
            problems, warnings, tools = validate_skill_code(code, taken)
            if old_code is not None and _normalized(code) == _normalized(old_code):
                problems.insert(0, "Кодът е същият като досегашния — нищо не е поправено. Намери "
                                   "причината за проблема и промени кода така, че да я отстрани.")
            if not problems:
                return code, warnings, tools, attempt
            self.progress(f"опит {attempt} не мина проверката: {problems[0]}")
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": "Проверката откри проблеми:\n- " + "\n- ".join(problems)
                 + "\nПоправи ги и върни ЦЕЛИЯ файл отново в един ```python блок."},
            ]
        raise ForgeError("Не успях да напиша код, който минава проверките: " + "; ".join(problems[:3]))

    # --- Archive ----------------------------------------------------------------------------
    def _archive(self, path: Path, suffix: str, content: str = "") -> None:
        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        (self.history_dir / f"{path.stem}__{stamp}{suffix}").write_text(content, encoding="utf-8")

    def _activate(self, proposal: Proposal) -> list[str]:
        """Writes the file and loads it. On failure restores the old version."""
        path = proposal.file
        if proposal.old_code is None:
            self._archive(path, ".created")
        else:
            self._archive(path, ".bak", proposal.old_code)
        path.write_text(proposal.code, encoding="utf-8")
        try:
            return self.registry.load_skill_file(path)
        except BaseException as e:
            if proposal.old_code is None:
                path.unlink(missing_ok=True)
                self.registry.unload_skill_file(path)
            else:
                path.write_text(proposal.old_code, encoding="utf-8")
                self.registry.load_skill_file(path)
            raise ForgeError(f"Кодът не се зареди ({type(e).__name__}: {e}); върнах предишното състояние.")

    def _propose(self, proposal: Proposal) -> str:
        self.progress("чакам одобрение от сър")
        if not self.approve(proposal):
            return "Сър отказа промяната. Нищо не е променено."
        names = self._activate(proposal)
        self.progress(f"включено: {', '.join(names)}")
        verb = "създадено и включено" if proposal.kind == "create" else "поправено и презаредено"
        return (f"Умението е {verb}: {', '.join(names)}. СЕГА го извикай, за да изпълниш молбата "
                f"на сър, и отговори с истинския му резултат — не измисляй резултата.")

    # --- Public operations (called by the skills in skills/self_improvement.py) ---------------------
    def create(self, name: str, description: str) -> str:
        stem = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_") or "new_skill"
        if stem[0].isdigit():
            stem = f"skill_{stem}"
        path = self.skills_dir / f"{stem}.py"
        if path.exists() or stem in self.registry.names():
            return f"Вече има умение или файл „{stem}“. Използвай improve_skill, за да го промениш."
        task = (f"Напиши нов файл с умение. Име на функцията: {stem}.\n"
                f"Какво трябва да прави (по думите на сър): {description}")
        code, warnings, tools, attempts = self._write_code(task, own_names=set())
        return self._propose(Proposal("create", f"Ново умение · {stem}", description, path,
                                      code, None, warnings, tools, attempts))

    def improve(self, skill_name: str, problem: str) -> str:
        path = self.registry.source_file(skill_name) or self.skills_dir / f"{skill_name}.py"
        if not path.exists():
            known = ", ".join(self.registry.names())
            return f"Няма умение „{skill_name}“. Налични: {known}."
        if path.name in self.PROTECTED:
            return "Системата за самоусъвършенстване е защитена и не може да се променя сама."
        own = {n for n in self.registry.names() if self.registry.source_file(n) == path}
        errors = [e for e in self.registry.errors if e["tool"] in own][-3:]
        error_text = "\n\n".join(f"Извикване: {e['tool']}({e['arguments']})\n{e['traceback']}" for e in errors)
        old_code = path.read_text(encoding="utf-8")
        task = (f"Поправи/подобри този файл с умения. Запази всички съществуващи умения, освен ако "
                f"проблемът не изисква друго.\n\nПроблем (по думите на сър): {problem}\n\n"
                + (f"Последни грешки при изпълнение:\n{error_text}\n\n" if error_text else "")
                + f"Текущ файл {path.name}:\n```python\n{old_code}```")
        code, warnings, tools, attempts = self._write_code(task, own_names=own, old_code=old_code)
        missing = own - set(tools)
        if missing:
            warnings.append(f"премахва умения: {', '.join(sorted(missing))}")
        return self._propose(Proposal("improve", f"Поправка · {path.stem}", problem, path,
                                      code, old_code, warnings, tools, attempts))

    def undo(self, skill_name: str) -> str:
        path = self.registry.source_file(skill_name) or self.skills_dir / f"{skill_name}.py"
        entries = sorted(self.history_dir.glob(f"{path.stem}__*.bak")) + sorted(self.history_dir.glob(f"{path.stem}__*.created"))
        if not entries:
            return f"Няма запазени предишни версии на „{skill_name}“."
        latest = max(entries, key=lambda p: p.stem.rsplit("__", 1)[1])
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        self._archive(path, ".undone", current)
        if latest.suffix == ".created":
            path.unlink(missing_ok=True)
            self.registry.unload_skill_file(path)
            message = f"Премахнах новото умение „{path.stem}“."
        else:
            path.write_text(modernize(latest.read_text(encoding="utf-8")), encoding="utf-8")
            self.registry.load_skill_file(path)
            message = f"Върнах предишната версия на „{path.stem}“."
        latest.unlink()
        return message

    def recent_errors(self) -> str:
        errors = list(self.registry.errors)[-5:]
        if not errors:
            return "Няма записани грешки на умения в тази сесия."
        return "\n".join(f"{e['time']} {e['tool']}: {e['error']}" for e in errors)


# Shared instances — used by the skills (skills/self_improvement.py), the core and the app.
lessons = LessonBook(config.BASE_DIR / "memory" / "lessons.json")
forge = SkillForge(registry, config.SKILLS_DIR)


# =====================================================================================
#  Reflection — learning from remarks, whether or not the model remembered to call learn_lesson
# =====================================================================================
CORRECTION_RE = re.compile(
    r"\b(грешиш|грешно|сгреши|объркал|не е вярно|не е така|не е правилно|не така|не прави|не казвай|"
    r"недей|спри да|винаги|никога|занапред|от сега нататък|предпочитам|не ми харесва|по-добре е)\b",
    re.IGNORECASE,
)

LESSON_PROMPT = """Анализираш разговор между сър и неговия AI асистент Орион.
Предишен отговор на Орион: «{answer}»
Реплика на сър: «{user}»

Съдържа ли репликата на сър ТРАЙНО правило за това как Орион трябва да се държи или да отговаря
занапред (стил, формат, тон, предпочитание, поправка на грешка, която не бива да се повтаря)?
- Ако да: върни САМО правилото — едно кратко обобщено изречение в повелително наклонение,
  например „Казвай температурата в градуси Целзий.“
- Ако не — върни точно NONE.

Примери:
„Грешиш, казвай температурата в Целзий.“ -> Казвай температурата в градуси Целзий.
„Не ми казвай датата, когато питам колко е часът.“ -> Когато сър пита за часа, казвай само часа и минутите.
„Никога не ме наричай по име.“ -> Не наричай сър по име.
„Поправи умението get_weather, дава грешка.“ -> NONE
„Колко е часът?“ -> NONE
„Благодаря.“ -> NONE"""


class Reflector:
    def __init__(self, lessons: LessonBook, forge: SkillForge):
        self.lessons = lessons
        self.forge = forge

    def after_turn(self, user_text: str, previous_answer: str, tools_used: list[str]) -> str | None:
        """Returns the learned lesson (or None). Called after every answer."""
        # Code fixes are made by the forge; they are not behaviour lessons.
        handled = {"learn_lesson", "create_skill", "improve_skill", "undo_skill_change", "remember"}
        if handled & set(tools_used) or not CORRECTION_RE.search(user_text) or self.forge.client is None:
            return None
        try:
            reply = self.forge.client.chat.completions.create(
                model=self.forge.model, temperature=0, **self.forge.thinking("none"),
                messages=[{"role": "user", "content": LESSON_PROMPT.format(answer=previous_answer[:600],
                                                                          user=user_text)}],
            ).choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001 — reflection must never break the conversation
            print(f"[Рефлексия] {e}")
            return None
        lesson = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip().strip("\"'«»„“ ")
        if not lesson or lesson.upper().startswith("NONE") or len(lesson) > 300:
            return None
        self.lessons.add(lesson)
        return lesson


reflector = Reflector(lessons, forge)
