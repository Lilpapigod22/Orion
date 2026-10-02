"""
The skill system (Tools / Function Calling).

Adding a new skill is one Python function with a decorator:

    from orion import orion_tool

    @orion_tool
    def get_time(city: str) -> str:
        '''Returns the current time in a given city.

        Args:
            city: The name of the city.
        '''
        ...

From the signature (types, default values) and the docstring, a JSON schema is
generated automatically, which the LLM uses to decide when and how to call the function.
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

# Mapping between Python types and JSON Schema types.
_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def _parse_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Splits a docstring into the general description and parameter descriptions (the `Args:` section)."""
    doc = inspect.cleandoc(doc or "")
    description, _, args_block = doc.partition("Args:")
    param_docs = {}
    for line in args_block.splitlines():
        match = re.match(r"\s*(\w+)\s*(?:\([^)]*\))?\s*:\s*(.+)", line)
        if match:
            param_docs[match.group(1)] = match.group(2).strip()
    return description.strip(), param_docs


class OrionTools:
    """Registry of all the skills Orion can use."""

    def __init__(self):
        self._tools: dict[str, dict] = {}  # name -> {"func": ..., "schema": ..., "module": ...}
        self._files: dict[str, Path] = {}  # module -> the file it was loaded from
        # The latest skill errors — Orion reads them when it repairs itself.
        self.errors: deque[dict] = deque(maxlen=30)

    # --- Registration ----------------------------------------------------------
    def tool(self, func: Callable | None = None, *, name: str | None = None, description: str | None = None):
        """Decorator. Can be used as `@tool` or `@tool(name=..., description=...)`."""

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

    # --- Use by the AI core -----------------------------------------------------
    def schemas(self, exclude_modules: set[str] | frozenset = frozenset()) -> list[dict]:
        """The skill descriptions for the model — without those from `exclude_modules` (see orion/router.py)."""
        return [t["schema"] for t in self._tools.values() if t["module"] not in exclude_modules]

    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> list[tuple[str, str]]:
        """(name, description) of all skills."""
        return [(n, t["schema"]["function"]["description"]) for n, t in self._tools.items()]

    def source_file(self, name: str) -> Path | None:
        """The file the skill is written in."""
        tool = self._tools.get(name)
        return self._files.get(tool["module"]) if tool else None

    def call(self, name: str, arguments: str | dict | None) -> str:
        """Runs a skill by name. Errors are returned as text so the model can react."""
        if name not in self._tools:
            return f"Грешка: няма умение с име '{name}'."
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments or "{}")
            result = self._tools[name]["func"](**(arguments or {}))
            return str(result)
        except Exception as e:  # noqa: BLE001 — every error is reported to the model
            self.errors.append({
                "tool": name,
                "arguments": arguments,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(limit=6),
                "time": f"{datetime.now():%H:%M:%S}",
            })
            return f"Грешка при изпълнение на '{name}': {type(e).__name__}: {e}"

    # --- Automatic plugin loading --------------------------------------------
    def load_skills(self, folder: Path) -> None:
        """Imports every .py file in the folder (except those starting with '_').

        Importing runs the @orion_tool decorators, which registers the skills.
        """
        for path in sorted(Path(folder).glob("*.py")):
            if not path.name.startswith("_"):
                try:
                    self.load_skill_file(path)
                except Exception as e:  # noqa: BLE001 — one broken plugin does not stop Orion
                    print(f"[Умения] Неуспешно зареждане на {path.name}: {e}")

    def load_skill_file(self, path: Path) -> list[str]:
        """(Re)loads one skill file without a restart. Returns the names of its skills.

        On error the file's old skills stay active.
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
            self._tools.update(previous)  # Restore the working version.
            raise
        self._files[module_name] = path
        return [n for n, t in self._tools.items() if t["module"] == module_name]

    def unload_skill_file(self, path: Path) -> None:
        module_name = f"skills.{Path(path).stem}"
        for n in [n for n, t in self._tools.items() if t["module"] == module_name]:
            del self._tools[n]
        self._files.pop(module_name, None)
        sys.modules.pop(module_name, None)


# Global registry + a short alias for the decorator.
registry = OrionTools()
orion_tool = registry.tool
