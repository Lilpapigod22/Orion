"""
Краткосрочна памет — историята на разговора.

Пази и извикванията на умения с (съкратените) им резултати: ако моделът вижда в историята
само готови отговори, започва да им подражава и да отговаря, без да използва умения.
Записва се във файл, така че Орион помни последния разговор и след рестарт.
"""
import json
import time
from collections import deque
from pathlib import Path


class ConversationMemory:
    def __init__(self, max_turns: int = 12, path: Path | None = None, keep_hours: float = 12):
        # Всеки елемент е една реплика: [въпрос, (извикване, резултат)…, отговор]; старите отпадат.
        self._turns: deque[dict] = deque(maxlen=max_turns)
        self.path = Path(path) if path else None
        self.keep_seconds = keep_hours * 3600
        self._load()

    def add_turn(self, user_text: str, assistant_text: str, steps: list[dict] | None = None) -> None:
        """`steps` — съобщенията с извиквания на умения и резултатите им (формат на LLM API-то)."""
        self._turns.append({"time": time.time(), "messages": [
            {"role": "user", "content": user_text}, *(steps or []),
            {"role": "assistant", "content": assistant_text}]})
        self._save()

    def as_messages(self) -> list[dict]:
        """Връща историята във формата на съобщения за LLM API-то."""
        return [message for turn in self._turns for message in turn["messages"]]

    def last_user_text(self) -> str:
        return self._turns[-1]["messages"][0]["content"] if self._turns else ""

    def last_assistant_text(self) -> str:
        return self._turns[-1]["messages"][-1]["content"] if self._turns else ""

    def clear(self) -> None:
        self._turns.clear()
        self._save()

    # --- Файл -----------------------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path:
            return
        try:
            turns = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        # Само скорошният разговор: вчерашният би объркал днешните въпроси.
        fresh = [t for t in turns if time.time() - t.get("time", 0) < self.keep_seconds]
        self._turns.extend(fresh[-self._turns.maxlen:])

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(list(self._turns), ensure_ascii=False), encoding="utf-8")
        except OSError as e:  # паметта не бива да спира разговора
            print(f"[Памет] Не успях да запиша разговора: {e}")


def tool_steps(call_id: str, name: str, arguments: str, result: str) -> list[dict]:
    """Едно извикване на умение като съобщения за паметта (напр. от рефлекс)."""
    return [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}]},
        {"role": "tool", "tool_call_id": call_id, "content": result[:600]},
    ]
