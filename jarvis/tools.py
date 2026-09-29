"""
Система за Умения (Tools / Function Calling).

Добавянето на ново умение е едно Python функция с декоратор:

    from jarvis import jarvis_tool

    @jarvis_tool
    def get_time(city: str) -> str:
        '''Връща текущия час в даден град.

        Args:
            city: Името на града.
        '''
        ...

От сигнатурата (типове, стойности по подразбиране) и docstring-а автоматично се
генерира JSON схема, която LLM-ът използва, за да реши кога и как да извика функцията.
"""
import importlib.util
import inspect
import json
import re
import sys
import traceback
import typing
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

# Съответствие между Python типове и JSON Schema типове.
_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def _parse_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Разделя docstring на общо описание и описания на параметрите (секция `Args:`)."""
    doc = inspect.cleandoc(doc or "")
    description, _, args_block = doc.partition("Args:")
    param_docs = {}
    for line in args_block.splitlines():
        match = re.match(r"\s*(\w+)\s*(?:\([^)]*\))?\s*:\s*(.+)", line)
        if match:
            param_docs[match.group(1)] = match.group(2).strip()
    return description.strip(), param_docs


class JarvisTools:
    """Регистър на всички умения, които JARVIS може да използва."""

    def __init__(self):
        self._tools: dict[str, dict] = {}  # име -> {"func": ..., "schema": ..., "module": ...}
        self._files: dict[str, Path] = {}  # модул -> файл, от който е зареден
        # Последните грешки на уменията — JARVIS ги чете, когато се самопоправя.
        self.errors: deque[dict] = deque(maxlen=30)

    # --- Регистриране ----------------------------------------------------------
    def tool(self, func: Callable | None = None, *, name: str | None = None, description: str | None = None):
        """Декоратор. Може да се ползва като `@tool` или `@tool(name=..., description=...)`."""

        def register(f: Callable) -> Callable:
            tool_name = name or f.__name__
            doc_description, param_docs = _parse_docstring(f.__doc__)
            hints = typing.get_type_hints(f)

            properties, required = {}, []
            for param in inspect.signature(f).parameters.values():
                json_type = _JSON_TYPES.get(hints.get(param.name, str), "string")
                prop = {"type": json_type}
                if param.name in param_docs:
                    prop["description"] = param_docs[param.name]
                properties[param.name] = prop
                if param.default is inspect.Parameter.empty:
                    required.append(param.name)

            self._tools[tool_name] = {
                "func": f,
                "module": f.__module__,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": description or doc_description or tool_name,
                        "parameters": {"type": "object", "properties": properties, "required": required},
                    },
                },
            }
            return f

        return register(func) if func is not None else register

    # --- Използване от AI ядрото ------------------------------------------------
    def schemas(self, exclude_modules: set[str] | frozenset = frozenset()) -> list[dict]:
        """Описанията на уменията за модела — без тези от `exclude_modules` (виж jarvis/router.py)."""
        return [t["schema"] for t in self._tools.values() if t["module"] not in exclude_modules]

    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> list[tuple[str, str]]:
        """(име, описание) на всички умения."""
        return [(n, t["schema"]["function"]["description"]) for n, t in self._tools.items()]

    def source_file(self, name: str) -> Path | None:
        """Файлът, в който е написано умението."""
        tool = self._tools.get(name)
        return self._files.get(tool["module"]) if tool else None

    def call(self, name: str, arguments: str | dict | None) -> str:
        """Изпълнява умение по име. Грешките се връщат като текст, за да може моделът да реагира."""
        if name not in self._tools:
            return f"Грешка: няма умение с име '{name}'."
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments or "{}")
            result = self._tools[name]["func"](**(arguments or {}))
            return str(result)
        except Exception as e:  # noqa: BLE001 — всяка грешка се докладва на модела
            self.errors.append({
                "tool": name,
                "arguments": arguments,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(limit=6),
                "time": f"{datetime.now():%H:%M:%S}",
            })
            return f"Грешка при изпълнение на '{name}': {type(e).__name__}: {e}"

    # --- Автоматично зареждане на плъгини --------------------------------------
    def load_skills(self, folder: Path) -> None:
        """Импортира всеки .py файл от папката (без тези, започващи с '_').

        Импортирането изпълнява декораторите @jarvis_tool и така уменията се регистрират.
        """
        for path in sorted(Path(folder).glob("*.py")):
            if not path.name.startswith("_"):
                try:
                    self.load_skill_file(path)
                except Exception as e:  # noqa: BLE001 — един счупен плъгин не спира JARVIS
                    print(f"[Умения] Неуспешно зареждане на {path.name}: {e}")

    def load_skill_file(self, path: Path) -> list[str]:
        """(Пре)зарежда един файл с умения без рестарт. Връща имената на уменията в него.

        При грешка старите умения от файла остават активни.
        """
        path = Path(path)
        module_name = f"skills.{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        previous = {n: t for n, t in self._tools.items() if t["module"] == module_name}
        for n in previous:
            del self._tools[n]
        try:
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except BaseException:
            self._tools.update(previous)  # Връщаме работещата версия.
            raise
        self._files[module_name] = path
        return [n for n, t in self._tools.items() if t["module"] == module_name]

    def unload_skill_file(self, path: Path) -> None:
        module_name = f"skills.{Path(path).stem}"
        for n in [n for n, t in self._tools.items() if t["module"] == module_name]:
            del self._tools[n]
        self._files.pop(module_name, None)
        sys.modules.pop(module_name, None)


# Глобален регистър + кратък псевдоним за декоратора.
registry = JarvisTools()
jarvis_tool = registry.tool
