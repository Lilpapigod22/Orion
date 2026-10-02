"""
Streamed model answers. The text and the reasoning arrive piece by piece — for the live board and for
cancelling (test mode) — but the caller gets the same message as from a normal call: content,
tool_calls, reasoning (in model_extra).
"""
from types import SimpleNamespace
from typing import Callable


def _stop_if_needed(check: Callable[[], type[Exception] | None] | None) -> None:
    reason = check() if check else None
    if reason:
        raise reason()


def _tell(on_delta: Callable[[str, str], None] | None, kind: str, text: str) -> None:
    if on_delta:
        try:
            on_delta(kind, text)
        except Exception as e:  # noqa: BLE001 — an observer must never break the answer
            print(f"[Streaming] {e}")


def create_streamed(client, *, on_delta: Callable[[str, str], None] | None = None,
                    check: Callable[[], type[Exception] | None] | None = None, **kwargs):
    """`client.chat.completions.create(**kwargs)`, streamed. `check()` returns an exception class to stop."""
    _stop_if_needed(check)
    stream = client.chat.completions.create(stream=True, **kwargs)
    content, reasoning, calls = [], [], []
    try:
        for chunk in stream:
            _stop_if_needed(check)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content.append(delta.content)
                _tell(on_delta, "content", delta.content)
            extra = getattr(delta, "model_extra", None) or {}
            if extra.get("reasoning"):
                reasoning.append(extra["reasoning"])
                _tell(on_delta, "reasoning", extra["reasoning"])
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
        close = getattr(stream, "close", None)
        if close:
            close()
    tool_calls = [SimpleNamespace(id=c["id"] or f"call_{i}", type="function",
                                  function=SimpleNamespace(name=c["name"], arguments=c["arguments"] or "{}"))
                  for i, c in enumerate(calls)]
    message = SimpleNamespace(content="".join(content), tool_calls=tool_calls or None,
                              model_extra={"reasoning": "".join(reasoning)} if reasoning else {})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])
