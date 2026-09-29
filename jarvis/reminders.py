"""
Напомняния и таймери. Пазят се в memory/reminders.json, за да оцелеят след рестарт.
Приложението проверява на всеки няколко секунди кои са настъпили и ги казва на глас.
"""
import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class ReminderBook:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, text: str, due: datetime, kind: str = "reminder", repeat_minutes: int = 0, times: int = 0) -> dict:
        """kind: "reminder" (напомняне) или "timer" (таймер). С `repeat_minutes` — повтаря се `times` пъти."""
        item = {"id": uuid.uuid4().hex[:8], "text": text.strip(), "due": due.isoformat(timespec="seconds"),
                "kind": kind}
        if repeat_minutes > 0:
            item["repeat"], item["left"] = repeat_minutes, max(1, times)
        with self._lock:
            items = self._load()
            items.append(item)
            self._save(sorted(items, key=lambda i: i["due"]))
        return item

    def pending(self) -> list[dict]:
        with self._lock:
            return self._load()

    def pop_due(self, now: datetime | None = None) -> list[dict]:
        """Маха и връща напомнянията, чийто час е дошъл."""
        now = (now or datetime.now()).isoformat(timespec="seconds")
        with self._lock:
            items = self._load()
            due = [i for i in items if i["due"] <= now]
            if due:
                rest = [i for i in items if i["due"] > now]
                for item in due:  # повтарящите се — отново след `repeat` минути
                    if item.get("repeat") and item.get("left", 1) > 1:
                        again = dict(item, left=item["left"] - 1, due=(datetime.fromisoformat(item["due"])
                                     + timedelta(minutes=item["repeat"])).isoformat(timespec="seconds"))
                        rest.append(again)
                self._save(sorted(rest, key=lambda i: i["due"]))
        return due

    def cancel(self, query: str = "") -> list[dict]:
        """Отменя напомнянията, чийто текст съдържа `query` (празно — всички)."""
        query = query.lower().strip()
        with self._lock:
            items = self._load()
            removed = [i for i in items if query in i["text"].lower() or query == i["id"]]
            self._save([i for i in items if i not in removed])
        return removed


book = ReminderBook(BASE_DIR / "memory" / "reminders.json")
