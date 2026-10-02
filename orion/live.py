"""
The step recorder — what Orion is doing right now, for the live board in the window.

One request = one trace: begin() -> start()/update()/finish() for each step -> end(). Every call sends a
small event to `sink` (the app points it at the window). Nothing here may break or slow an answer: a
failing sink is reported once and ignored, and calls outside a trace (reminders, alerts) are ignored.
"""
import itertools
import threading
import time
from typing import Callable

PHASES = ("heard", "understood", "thinking", "skill", "speaking", "done")

sink: Callable[[dict], None] | None = None

_ids = itertools.count(1)
_lock = threading.RLock()
_trace: dict | None = None
_sink_failed = False


def _emit(event: dict) -> None:
    global _sink_failed
    if sink is None:
        return
    try:
        sink(event)
    except Exception as e:  # noqa: BLE001 — the board must never break an answer
        if not _sink_failed:
            _sink_failed = True
            print(f"[Live] the window did not take a step: {e}")


def _event(phase: str, state: str, label: str, detail: dict | None = None, key: str | None = None,
           ms: int | None = None, ok: bool | None = None) -> dict:
    return {"trace": _trace["id"], "phase": phase, "state": state, "label": str(label)[:300], "detail": detail,
            "key": key or phase, "t": round(time.monotonic() - _trace["start"], 3), "ms": ms, "ok": ok}


def current() -> int | None:
    return _trace["id"] if _trace else None


def begin(text: str, source: str = "text", heard: dict | None = None) -> int:
    """A new request. The first event is the finished „heard" step (typed or recognised text)."""
    global _trace
    with _lock:
        _trace = {"id": next(_ids), "start": time.monotonic(), "open": {}, "ok": True}
        _emit(_event("heard", "end", text, {"source": source, **(heard or {})}, ms=(heard or {}).get("ms"), ok=True))
        return _trace["id"]


def start(phase: str, label: str, detail: dict | None = None, key: str | None = None) -> None:
    with _lock:
        if _trace is None:
            return
        _trace["open"][key or phase] = time.monotonic()
        _emit(_event(phase, "start", label, detail, key))


def update(phase: str, label: str, detail: dict | None = None, key: str | None = None) -> None:
    with _lock:
        if _trace is not None:
            _emit(_event(phase, "update", label, detail, key))


def finish(phase: str, label: str = "", detail: dict | None = None, ok: bool = True, key: str | None = None) -> None:
    with _lock:
        if _trace is None:
            return
        began = _trace["open"].pop(key or phase, None)
        ms = round((time.monotonic() - began) * 1000) if began is not None else None
        if not ok:
            _trace["ok"] = False
        _emit(_event(phase, "end", label, detail, key, ms, ok))


def fail() -> None:
    with _lock:
        if _trace is not None:
            _trace["ok"] = False


def end(ok: bool | None = None) -> None:
    global _trace
    with _lock:
        if _trace is None:
            return
        ok = _trace["ok"] if ok is None else ok
        ms = round((time.monotonic() - _trace["start"]) * 1000)
        _emit(_event("done", "end", "done" if ok else "failed", None, "done", ms, ok))
        _trace = None
