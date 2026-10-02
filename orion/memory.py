"""
Short-term memory — the conversation history.

It also keeps skill calls with their (shortened) results: if the model only sees finished
answers in the history, it starts imitating them and answering without using skills.
It is saved to a file, so Orion remembers the last conversation after a restart.
"""
import json
import time
from collections import deque
from pathlib import Path


class ConversationMemory:
    def __init__(self, max_turns: int = 12, path: Path | None = None, keep_hours: float = 12):
        # Each item is one exchange: [question, (call, result)…, answer]; old ones drop off.
        self._turns: deque[dict] = deque(maxlen=max_turns)
        self.path = Path(path) if path else None
        self.keep_seconds = keep_hours * 3600
        self._load()

    def add_turn(self, user_text: str, assistant_text: str, steps: list[dict] | None = None) -> None:
        """`steps` — the messages with skill calls and their results (LLM API format)."""
        self._turns.append({"time": time.time(), "messages": [
            {"role": "user", "content": user_text}, *(steps or []),
            {"role": "assistant", "content": assistant_text}]})
        self._save()

    def as_messages(self) -> list[dict]:
        """Returns the history as messages for the LLM API."""
        return [message for turn in self._turns for message in turn["messages"]]

    def last_user_text(self) -> str:
        return self._turns[-1]["messages"][0]["content"] if self._turns else ""

    def last_assistant_text(self) -> str:
        return self._turns[-1]["messages"][-1]["content"] if self._turns else ""

    def clear(self) -> None:
        self._turns.clear()
        self._save()

    # --- File -----------------------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path:
            return
        try:
            turns = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        # Only the recent conversation: yesterday's would confuse today's questions.
        fresh = [t for t in turns if time.time() - t.get("time", 0) < self.keep_seconds]
        self._turns.extend(fresh[-self._turns.maxlen:])

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(list(self._turns), ensure_ascii=False), encoding="utf-8")
        except OSError as e:  # memory must never stop the conversation
            print(f"[Памет] Не успях да запиша разговора: {e}")


def tool_steps(call_id: str, name: str, arguments: str, result: str) -> list[dict]:
    """One skill call as memory messages (e.g. from a reflex)."""
    return [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}]},
        {"role": "tool", "tool_call_id": call_id, "content": result[:600]},
    ]
