# 3D Eyes and Live Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Orion's reactor with glowing 3D robot eyes whose expressions follow its real state, and add a live board (step pipeline, step details, gauges, background jobs) that shows what Orion is doing at every moment.

**Architecture:** Python records every step of a request in `orion/live.py` and streams it to the window; the brain streams model output through `orion/streaming.py`; `orion/telemetry.py` samples GPU/CPU once a second. The React window keeps the 2D skill network (`engine/mind.js`, minus the reactor) and puts an R3F WebGL canvas with bloom (or a 2D fallback) in its centre; pure engine modules (`expression.js`, `eyesRig.js`, `live.js`) hold the logic so it is unit-testable.

**Tech Stack:** Python 3.12, pytest, psutil, nvidia-smi · React 19, Vite 8, three 0.186, @react-three/fiber 9, @react-three/postprocessing 3 + postprocessing 6, motion 14, Vitest 5, @testing-library/react 16, jsdom · headless Microsoft Edge for browser checks.

**Spec:** `docs/superpowers/specs/2026-10-02-eyes-live-board-design.md`

## Global Constraints

- All visible window text in English; everything Orion *says* stays Bulgarian.
- The built window must stay one classic IIFE script with relative paths (`ui/index.html` is opened from `file://`).
- Eyes render at most 30 fps, DPR ≤ 1.5, and pause when `document.hidden`; WebGL failure → 2D eyes.
- Nothing on the board may block, slow or break an answer: every emitter is fire-and-forget inside try/except.
- Telemetry runs once per second and only while the window is not minimised; `nvidia-smi` runs with `CREATE_NO_WINDOW`, 2 s timeout, dropped after 3 failures in a row.
- Performance targets: GPU ≤ +10 points and video memory ≤ +150 MB versus the Task 1 baseline; answer time for the same typed question grows ≤ 5 %.
- Existing safety rules stay: confirm buttons, code approval, sandbox in test mode.
- **No git commits unless sir asks** (standing rule) — every task ends with a checkpoint (all tests green) instead of a commit.
- Before restarting the real Orion window (it closes sir's running Orion), tell sir in one line.
- Bash heredocs turn `\b` into a backspace character in Python sources — write regex/code with the Write/Edit tools, never through a heredoc'd Python string.

## Review Focus

1. A very long reasoning stream (thousands of pieces) — the window must stay responsive: updates are throttled to one per 0.15 s (test in Task 5).
2. Window minimised during an answer — gauges stop, eyes stop rendering, the answer still completes (gauges: test in Task 4; eyes: jsdom has no real visibility, so the minimise/restore check is in Task 10 Step 2 with the real window).
3. WebGL missing or the 3D context failing — 2D eyes appear instead, no blank centre (test in Task 8).
4. Live events for an unknown or already finished trace, or out of order (a late skill end after `done`) — ignored without errors (test in Task 6).
5. Test mode's sandbox brain (its client already streams) — answers still work, no double `stream` argument (test in Task 3).

---

### Task 1: Test tooling and baseline measurements

**Files:**
- Create: `tests/conftest.py`, `tests/test_smoke.py`
- Create: `web/e2e/stub.js`, `web/e2e/interact.js`, `web/e2e/interact.html`, `web/e2e/run.py`
- Modify: `web/package.json` (scripts, devDependencies), `web/vite.config.js` (vitest block)
- Create: `web/src/util.test.js`
- Create: `docs/superpowers/plans/2026-10-02-baseline.md` (measured numbers)

**Interfaces:**
- Produces: `python -m pytest -q` (Python suite), `npm test` in `web/` (Vitest), `python web/e2e/run.py` (browser checks, exit code 1 on failure).

- [ ] **Step 1: Install pytest and the web test packages**

```bash
python -m pip install pytest
cd web && npm install --no-fund --no-audit -D vitest@5.0.3 @testing-library/react@16.3.3 jsdom@30.1.1
```

- [ ] **Step 2: Write the Python smoke test**

`tests/conftest.py`:
```python
"""Tests run from the project root: `python -m pytest -q`."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

`tests/test_smoke.py`:
```python
from orion import reflexes


def test_quick_command_is_recognised():
    reflex = reflexes.respond("Хвърли монета")
    assert reflex is not None and reflex.tool == "flip_coin"
```

- [ ] **Step 3: Run it**

Run: `python -m pytest -q`
Expected: `1 passed`

- [ ] **Step 4: Vitest config and smoke test**

In `web/package.json` add to `"scripts"`: `"test": "vitest run"`.

In `web/vite.config.js` add to the object passed to `defineConfig` (next to `build`):
```js
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],
  },
```

`web/src/util.test.js`:
```js
import { describe, expect, it } from 'vitest';
import { clockTime } from './util.js';

describe('clockTime', () => {
  it('pads hours and minutes', () => {
    expect(clockTime(new Date(2026, 0, 1, 7, 5, 9))).toBe('07:05');
    expect(clockTime(new Date(2026, 0, 1, 7, 5, 9), true)).toBe('07:05:09');
  });
});
```

Run: `cd web && npm test`
Expected: `1 passed`

- [ ] **Step 5: Move the browser harness into the repo**

Copy `stub.js` and `interact.js` from the session scratchpad folder `uitest/` to `web/e2e/` unchanged. `web/e2e/interact.html`:
```html
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>interact</title>
<script src="stub.js"></script>
<script defer src="../../ui/assets/orion.js"></script>
<link rel="stylesheet" href="../../ui/assets/style.css">
<script defer src="interact.js"></script>
</head><body><div id="root"></div></body></html>
```

`web/e2e/run.py`:
```python
"""Browser checks of the built window (ui/): python web/e2e/run.py — PASS/FAIL lines, exit code 1 on failure."""
import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
HERE = Path(__file__).resolve().parent


def main() -> int:
    with tempfile.TemporaryDirectory() as profile:
        dom = subprocess.run(
            [str(EDGE), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
             "--allow-file-access-from-files", "--window-size=1180,760", "--virtual-time-budget=15000",
             "--dump-dom", (HERE / "interact.html").as_uri()],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    if not found:
        print("no result — the page did not finish")
        return 1
    lines = html.unescape(found[1]).splitlines()
    print("\n".join(lines))
    failed = [line for line in lines if line.startswith("FAIL")]
    print(f"passed {len(lines) - len(failed)}, failed {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `python web/e2e/run.py`
Expected: `passed 29, failed 0`

- [ ] **Step 6: Record the baseline**

Tell sir that Orion will restart. With the current (old) window: relaunch Orion (`relaunch.sh` in the scratchpad), wait 20 s, sample `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits` 10 times 0.7 s apart while the window is visible and idle; then type „Колко е 17 по 23?“ three times (type.ps1) and read the `[Sir]` → `[Orion]` timestamps in `logs/orion.log`. Write the averages to `docs/superpowers/plans/2026-10-02-baseline.md`:
```markdown
# Baseline before the eyes (old window)
- GPU idle: <average %> · video memory: <average MB>
- „Колко е 17 по 23?“: <three answer times in s>, average <s>
```

- [ ] **Step 7: Checkpoint** — `python -m pytest -q`, `npm test`, `python web/e2e/run.py` all green.

---

### Task 2: Step recorder (`orion/live.py`)

**Files:**
- Create: `orion/live.py`
- Test: `tests/test_live.py`

**Interfaces:**
- Produces:
  - `live.sink: Callable[[dict], None] | None`
  - `live.begin(text: str, source: str = "text", heard: dict | None = None) -> int`
  - `live.start(phase: str, label: str, detail: dict | None = None, key: str | None = None) -> None`
  - `live.update(phase: str, label: str, detail: dict | None = None, key: str | None = None) -> None`
  - `live.finish(phase: str, label: str = "", detail: dict | None = None, ok: bool = True, key: str | None = None) -> None`
  - `live.fail() -> None`, `live.end(ok: bool | None = None) -> None`, `live.current() -> int | None`
  - Event dict: `{"trace": int, "phase": str, "state": "start"|"update"|"end", "label": str, "detail": dict|None, "key": str, "t": float, "ms": int|None, "ok": bool|None}`; phases `heard, understood, thinking, skill, speaking, done`.

- [ ] **Step 1: Write the failing tests**

`tests/test_live.py`:
```python
import pytest

from orion import live


@pytest.fixture
def events():
    seen = []
    live.sink = seen.append
    yield seen
    live.end()
    live.sink = None


def test_a_request_produces_ordered_steps(events):
    trace = live.begin("Хвърли монета", "voice", {"google": "хвърли монета", "whisper": "Хвърли монета.", "ms": 120})
    live.start("understood", "choosing")
    live.finish("understood", "quick command", {"command": "flip_coin"})
    live.start("skill", "flip_coin", {"args": {}}, key="flip_coin")
    live.finish("skill", "flip_coin", {"result": "Падна се ези."}, key="flip_coin")
    live.end()
    assert [(e["phase"], e["state"]) for e in events] == [
        ("heard", "end"), ("understood", "start"), ("understood", "end"),
        ("skill", "start"), ("skill", "end"), ("done", "end")]
    assert {e["trace"] for e in events} == {trace}
    assert events[0]["detail"] == {"source": "voice", "google": "хвърли монета", "whisper": "Хвърли монета.", "ms": 120}
    assert events[0]["ms"] == 120
    assert isinstance(events[4]["ms"], int) and events[4]["ms"] >= 0 and events[4]["key"] == "flip_coin"
    assert events[-1]["ok"] is True and isinstance(events[-1]["ms"], int)


def test_two_skills_are_closed_by_key(events):
    live.begin("x")
    live.start("skill", "a", key="a")
    live.start("skill", "b", key="b")
    live.finish("skill", "a", key="a")
    live.finish("skill", "b", ok=False, key="b")
    live.end()
    ends = [e for e in events if e["phase"] == "skill" and e["state"] == "end"]
    assert [(e["key"], e["ok"]) for e in ends] == [("a", True), ("b", False)]
    assert all(e["ms"] is not None for e in ends)
    assert events[-1]["ok"] is False  # a failed skill makes the whole request „failed“


def test_calls_outside_a_trace_are_ignored(events):
    live.start("speaking", "reminder")
    live.update("speaking", "x")
    live.finish("speaking", "x")
    live.end()
    assert events == [] and live.current() is None


def test_a_broken_window_never_breaks_the_answer(capsys):
    def broken(event):
        raise RuntimeError("window closed")
    live.sink = broken
    live.begin("x")
    live.start("thinking", "round 1")
    live.end()
    live.sink = None
    assert capsys.readouterr().out.count("[Live]") == 1  # reported once, not per event


def test_fail_marks_the_request_failed(events):
    live.begin("x")
    live.fail()
    live.end()
    assert events[-1]["phase"] == "done" and events[-1]["ok"] is False
```

- [ ] **Step 2: Run to see them fail**

Run: `python -m pytest tests/test_live.py -q`
Expected: FAIL — `ImportError: cannot import name 'live'`

- [ ] **Step 3: Implement**

`orion/live.py`:
```python
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
    """A new request. The first event is the finished „heard“ step (typed or recognised text)."""
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
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_live.py -q`
Expected: `5 passed`

- [ ] **Step 5: Checkpoint** — `python -m pytest -q` green.

---

### Task 3: Streamed model answers in the brain (`orion/streaming.py`)

**Files:**
- Create: `orion/streaming.py`
- Modify: `orion/brain.py` (imports; `Brain.__init__` adds `self.stream = True`; new `Brain._complete`; `Brain.think` gets `on_delta`, `on_step`)
- Modify: `orion/self_test.py` (`StoppableClient._create` delegates; `_test_brain` sets `brain.stream = False`)
- Test: `tests/test_streaming.py`, `tests/test_brain_stream.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `streaming.create_streamed(client, *, on_delta: Callable[[str, str], None] | None = None, check: Callable[[], type[Exception] | None] | None = None, **kwargs) -> SimpleNamespace` — same shape as `client.chat.completions.create(...)` without streaming: `.choices[0].message` with `.content: str`, `.tool_calls: list | None`, `.model_extra: dict` (`{"reasoning": str}` when present). `on_delta(kind, text)` with kind `"reasoning"` or `"content"`.
  - `Brain.think(user_text, on_tool=None, on_result=None, on_thought=None, on_delta=None, on_step=None) -> str`; `on_step(kind, info)` with kinds `"route"` (`{"hidden": list[str], "shown": list[str]}`), `"model_start"` (`{"round": int, "effort": str}`), `"model_end"` (`{"round": int, "seconds": float, "tokens": int, "tps": float}`).

- [ ] **Step 1: Write the failing tests**

`tests/test_streaming.py`:
```python
from types import SimpleNamespace

import pytest

from orion import streaming


def chunk(content=None, reasoning=None, calls=None):
    delta = SimpleNamespace(content=content, model_extra={"reasoning": reasoning} if reasoning else {}, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def call(index, id=None, name=None, args=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=args))


class FakeStream:
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False

    def __iter__(self):
        return iter(self.chunks)

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, chunks):
        self.stream = FakeStream(chunks)
        self.kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.stream


def test_pieces_are_joined_like_a_normal_answer():
    client = FakeClient([chunk(reasoning="Мисля "), chunk(reasoning="малко."), chunk(content="17 по 23 "), chunk(content="са 391.")])
    seen = []
    reply = streaming.create_streamed(client, on_delta=lambda kind, text: seen.append((kind, text)), model="m", messages=[])
    message = reply.choices[0].message
    assert message.content == "17 по 23 са 391."
    assert message.model_extra == {"reasoning": "Мисля малко."}
    assert message.tool_calls is None
    assert seen == [("reasoning", "Мисля "), ("reasoning", "малко."), ("content", "17 по 23 "), ("content", "са 391.")]
    assert client.kwargs["stream"] is True and client.kwargs["model"] == "m"
    assert client.stream.closed


def test_tool_call_pieces_are_merged():
    client = FakeClient([chunk(calls=[call(0, "c1", "calcu", '{"expr')]), chunk(calls=[call(0, None, "late", 'ession": "1+1"}')])])
    message = streaming.create_streamed(client).choices[0].message
    assert len(message.tool_calls) == 1
    assert message.tool_calls[0].id == "c1"
    assert message.tool_calls[0].function.name == "calculate"
    assert message.tool_calls[0].function.arguments == '{"expression": "1+1"}'


def test_a_broken_observer_does_not_break_the_answer():
    client = FakeClient([chunk(content="а"), chunk(content="б")])
    def broken(kind, text):
        raise RuntimeError("window gone")
    assert streaming.create_streamed(client, on_delta=broken).choices[0].message.content == "аб"


def test_check_stops_the_stream_and_closes_it():
    class Interrupted(Exception):
        pass
    client = FakeClient([chunk(content="а"), chunk(content="б")])
    calls = iter([None, None, Interrupted])
    with pytest.raises(Interrupted):
        streaming.create_streamed(client, check=lambda: next(calls))
    assert client.stream.closed
```

`tests/test_brain_stream.py`:
```python
from types import SimpleNamespace

from orion.brain import Brain
from tests.test_streaming import FakeStream, call, chunk

SCHEMA = {"type": "function", "function": {"name": "calculate", "description": "Maths",
                                           "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}}}}


class Tools:
    def names(self):
        return ["calculate"]

    def schemas(self, hidden=frozenset()):
        return [SCHEMA]

    def call(self, name, arguments):
        return "17 * 23 = 391"


class Knowledge:
    def build_context(self, text):
        return ""


class Memory:
    def last_user_text(self):
        return ""

    def last_assistant_text(self):
        return ""

    def as_messages(self):
        return []

    def add_turn(self, *args):
        pass


class Client:
    """First round: a tool call. Second round: the answer."""
    def __init__(self, rounds):
        self.rounds, self.kwargs = list(rounds), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        return self.rounds.pop(0)


def make_brain(client, stream=True):
    brain = Brain(Tools(), Knowledge(), Memory(), base_url="http://x", api_key="x", model="m", persona="p")
    brain.client, brain.stream = client, stream
    return brain


def test_streamed_think_reports_route_rounds_and_pieces():
    client = Client([FakeStream([chunk(calls=[call(0, "c1", "calculate", '{"expression": "17*23"}')])]),
                     FakeStream([chunk(content="17 по 23 "), chunk(content="са 391.")])])
    steps, pieces = [], []
    answer = make_brain(client).think("Колко е 17 по 23?", on_step=lambda kind, info: steps.append((kind, info)),
                                      on_delta=lambda kind, text: pieces.append(text))
    assert answer == "17 по 23 са 391."
    assert [kind for kind, _ in steps] == ["route", "model_start", "model_end", "model_start", "model_end"]
    assert "shown" in steps[0][1] and "hidden" in steps[0][1]
    end = steps[-1][1]
    assert end["round"] == 1 and end["tokens"] == 2 and end["tps"] >= 0
    assert pieces == ["17 по 23 ", "са 391."]
    assert all(k["stream"] is True for k in client.kwargs)


def test_test_mode_brain_does_not_stream_twice():
    message = SimpleNamespace(content="Добре.", tool_calls=None, model_extra={})
    client = Client([SimpleNamespace(choices=[SimpleNamespace(message=message)])])
    assert make_brain(client, stream=False).think("Здравей") == "Добре."
    assert "stream" not in client.kwargs[0]
```

- [ ] **Step 2: Run to see them fail**

Run: `python -m pytest tests/test_streaming.py tests/test_brain_stream.py -q`
Expected: FAIL — `ImportError: cannot import name 'streaming'`

- [ ] **Step 3: Implement `orion/streaming.py`**

```python
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
```

- [ ] **Step 4: Use it in the brain**

`orion/brain.py` — imports: add `import time` after `import re`; change `from . import clock, router` to `from . import clock, router, streaming`.

In `Brain.__init__`, after `self.route_extra = None` line add:
```python
        # Model answers arrive piece by piece (live board). Test mode's client streams by itself -> False.
        self.stream = True
```

Add the method after `_default_call`:
```python
    def _complete(self, on_delta: Callable[[str, str], None] | None, **kwargs):
        if self.stream:
            return streaming.create_streamed(self.client, on_delta=on_delta, **kwargs)
        return self.client.chat.completions.create(**kwargs)
```

Change the `think` signature and docstring:
```python
    def think(self, user_text: str, on_tool: Callable[[str, str], None] | None = None,
              on_result: Callable[[str, str], None] | None = None,
              on_thought: Callable[[str], None] | None = None,
              on_delta: Callable[[str, str], None] | None = None,
              on_step: Callable[[str, dict], None] | None = None) -> str:
        """Returns Orion's answer. Observers (for the window): `on_tool(name, arguments)` — before each
        skill, `on_result(name, result)` — after it, `on_thought(text)` — the model's whole reasoning,
        `on_delta(kind, text)` — each streamed piece („reasoning“/„content“), `on_step(kind, info)` —
        „route“ (which skill groups the model sees), „model_start“/„model_end“ for each model round."""
```

Right after `hidden = router.excluded_modules(...)` add:
```python
        step = (lambda kind, info: on_step(kind, info)) if on_step else (lambda kind, info: None)
        step("route", {"hidden": sorted(hidden), "shown": sorted(m for m in router.GROUPS if m not in hidden)})
```

Replace the `response = self.client.chat.completions.create(...)` block with:
```python
            step("model_start", {"round": round_index, "effort": effort or "default"})
            pieces = [0]
            started = time.monotonic()

            def delta(kind: str, text: str) -> None:
                pieces[0] += 1
                if on_delta:
                    on_delta(kind, text)

            response = self._complete(
                delta,
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                **({"tools": tool_schemas} if offer_tools else {}),
                **({"reasoning_effort": effort} if effort else {}),
            )
            seconds = time.monotonic() - started
            step("model_end", {"round": round_index, "seconds": round(seconds, 2), "tokens": pieces[0],
                               "tps": round(pieces[0] / seconds, 1) if seconds > 0 else 0.0})
```

- [ ] **Step 5: Reuse it in test mode**

`orion/self_test.py` — in `StoppableClient`, replace the whole body of `_create` with:
```python
    def _create(self, **kwargs):
        return streaming.create_streamed(self._client, check=self._check, **kwargs)
```
and add `from . import streaming` to the module's `from . import …` imports (keep `_stop_if_needed` only if still used elsewhere; delete it if pyflakes reports it unused). In `_test_brain`, after `brain.client = self.client` add `brain.stream = False  # the client streams (and stops) by itself`.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q && python -m pyflakes orion/brain.py orion/streaming.py orion/self_test.py`
Expected: all pass (`11 passed`), pyflakes silent.

- [ ] **Step 7: Live check with the real model** — `PYTHONIOENCODING=utf-8 python -c` script: `from main import build_brain; b = build_brain('orion-qwen3.5:9b'); print(b.think('Колко е 17 по 23?', on_step=print))` → answer contains `391`, `model_end` lines show `tps` > 0.

- [ ] **Step 8: Checkpoint** — pytest green; sandbox skill run (`selftest_run2.py skills` in the scratchpad) still `119/119`.

---

### Task 4: Gauges (`orion/telemetry.py`)

**Files:**
- Create: `orion/telemetry.py`
- Test: `tests/test_telemetry.py`

**Interfaces:**
- Produces: `telemetry.parse_nvidia(text: str) -> dict | None` (`{"gpu": int, "vramUsed": int, "vramTotal": int}`); `class Telemetry(send: Callable[[dict], None], visible: Callable[[], bool], interval: float = 1.0, run=subprocess.run)` with `.sample() -> dict` (`cpu`, `ram`, and the GPU fields when available), `.start()`, `.stop()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_telemetry.py`:
```python
import subprocess
import time
from types import SimpleNamespace

from orion import telemetry


def test_parse_nvidia():
    assert telemetry.parse_nvidia("22, 1451, 10240\n") == {"gpu": 22, "vramUsed": 1451, "vramTotal": 10240}
    assert telemetry.parse_nvidia("") is None
    assert telemetry.parse_nvidia("NVIDIA-SMI has failed") is None


def test_sample_has_cpu_ram_and_gpu():
    fake = lambda *a, **k: SimpleNamespace(stdout="40, 2000, 10240")
    data = telemetry.Telemetry(lambda g: None, lambda: True, run=fake).sample()
    assert data["gpu"] == 40 and data["vramUsed"] == 2000 and 0 <= data["cpu"] <= 100 and 0 <= data["ram"] <= 100


def test_missing_gpu_is_dropped_after_three_failures():
    calls = []
    def missing(*a, **k):
        calls.append(1)
        raise FileNotFoundError("nvidia-smi")
    t = telemetry.Telemetry(lambda g: None, lambda: True, run=missing)
    for _ in range(5):
        data = t.sample()
    assert "gpu" not in data and len(calls) == 3


def test_nothing_is_sent_while_the_window_is_hidden():
    sent = []
    t = telemetry.Telemetry(sent.append, lambda: False, interval=0.01,
                            run=lambda *a, **k: SimpleNamespace(stdout="1, 2, 3"))
    t.start()
    time.sleep(0.1)
    t.stop()
    assert sent == []


def test_values_are_sent_while_visible():
    sent = []
    t = telemetry.Telemetry(sent.append, lambda: True, interval=0.01,
                            run=lambda *a, **k: SimpleNamespace(stdout="1, 2, 3"))
    t.start()
    time.sleep(0.1)
    t.stop()
    assert sent and sent[0]["gpu"] == 1
```

- [ ] **Step 2: Run to see them fail**

Run: `python -m pytest tests/test_telemetry.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement**

`orion/telemetry.py`:
```python
"""
Gauges for the live board: GPU load and video memory (nvidia-smi), processor and memory (psutil).
Once a second and only while the window is visible. A missing source is left out; nvidia-smi is
dropped after three failures in a row (no NVIDIA card or driver).
"""
import subprocess
import threading
from typing import Callable

import psutil

QUERY = ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"]
_CREATE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def parse_nvidia(text: str) -> dict | None:
    lines = (text or "").strip().splitlines()
    if not lines:
        return None
    try:
        gpu, used, total = (float(part) for part in lines[0].split(","))
    except ValueError:
        return None
    return {"gpu": round(gpu), "vramUsed": round(used), "vramTotal": round(total)}


class Telemetry:
    def __init__(self, send: Callable[[dict], None], visible: Callable[[], bool], interval: float = 1.0,
                 run=subprocess.run):
        self._send, self._visible, self._interval, self._run = send, visible, interval, run
        self._gpu_failures = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        psutil.cpu_percent(interval=None)  # the first reading is always 0 — start the counter

    def sample(self) -> dict:
        data = {"cpu": round(psutil.cpu_percent(interval=None)), "ram": round(psutil.virtual_memory().percent)}
        if self._gpu_failures < 3:
            try:
                result = self._run(QUERY, capture_output=True, text=True, timeout=2, creationflags=_CREATE)
                gpu = parse_nvidia(result.stdout)
            except (OSError, subprocess.SubprocessError):
                gpu = None
            if gpu:
                data.update(gpu)
                self._gpu_failures = 0
            else:
                self._gpu_failures += 1
        return data

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                if self._visible():
                    self._send(self.sample())
            except Exception as e:  # noqa: BLE001 — gauges must never stop Orion
                print(f"[Telemetry] {e}")

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="telemetry")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_telemetry.py -q`
Expected: `5 passed`

- [ ] **Step 5: Checkpoint** — `python -m pytest -q` green.

---

### Task 5: Instrument the app (heard → understood → thinking → skill → speaking → done)

**Files:**
- Modify: `app.py` — imports (`live`, `telemetry`); `Orion.__init__` (new attributes); `start()` (telemetry); `_worker` (passes `source`); `_answer`; `_run_reflex` unchanged; `_think`; new `_model_step`, `_delta`; `_log_tool`; `_tool_done`; `_speak` split into `_speak` + `_voice_out`; `_hear`; `on_minimized` / `on_restored`
- Test: `tests/test_app_live.py`

**Interfaces:**
- Consumes: `live.*` (Task 2), `Brain.think(..., on_delta, on_step)` (Task 3), `telemetry.Telemetry` (Task 4).
- Produces (window calls): `hud.live(event)`, `hud.setGauges({...})`, `hud.toolDone(name, shown, ok, ms)` (4th argument new).

- [ ] **Step 1: Write the failing tests**

`tests/test_app_live.py`:
```python
import time

import app
import config
from orion import live
from orion.tools import registry


def make_app(hud_calls):
    if not registry.names():
        registry.load_skills(config.SKILLS_DIR)
    orion = app.Orion.__new__(app.Orion)
    orion.hud = lambda fn, *args: hud_calls.append((fn, args))
    orion.brain, orion.ready, orion.muted, orion.window = None, True, True, None
    orion.last_activity, orion._speech_gen = 0.0, 0
    orion._tool_started, orion._last_heard = {}, None
    orion._thinking_key, orion._delta_text, orion._delta_sent = "thinking", "", 0.0
    return orion


def test_a_quick_command_sends_every_step():
    events, hud_calls = [], []
    orion = make_app(hud_calls)
    live.sink = events.append
    try:
        orion._answer("Хвърли монета", "text")
    finally:
        live.sink = None
    assert [(e["phase"], e["state"]) for e in events] == [
        ("heard", "end"), ("understood", "start"), ("understood", "end"), ("skill", "start"), ("skill", "end"),
        ("speaking", "start"), ("speaking", "end"), ("done", "end")]
    skill_end = events[4]
    assert skill_end["key"] == "flip_coin" and skill_end["ok"] is True and isinstance(skill_end["ms"], int)
    tool_done = next(args for fn, args in hud_calls if fn == "toolDone")
    assert tool_done[0] == "flip_coin" and tool_done[2] is True and isinstance(tool_done[3], int)


def test_spoken_requests_carry_both_transcripts():
    events = []
    orion = make_app([])
    orion._last_heard = {"google": "хвърли монета", "whisper": "Хвърли монета.", "ms": 140}
    live.sink = events.append
    try:
        orion._answer("хвърли монета", "voice")
    finally:
        live.sink = None
    assert events[0]["detail"]["whisper"] == "Хвърли монета." and events[0]["ms"] == 140


def test_streamed_reasoning_is_throttled():
    events = []
    orion = make_app([])
    live.sink = events.append
    try:
        live.begin("x")
        orion._model_step("model_start", {"round": 0, "effort": "low"})
        started = time.monotonic()
        for _ in range(2000):
            orion._delta("reasoning", "дума ")
        elapsed = time.monotonic() - started
        live.end()
    finally:
        live.sink = None
    updates = [e for e in events if e["state"] == "update"]
    assert 1 <= len(updates) <= elapsed / 0.15 + 2
    assert len(updates[-1]["detail"]["text"]) <= 600
```

- [ ] **Step 2: Run to see them fail**

Run: `python -m pytest tests/test_app_live.py -q`
Expected: FAIL — `_answer() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Implement in `app.py`**

Imports: change the `from orion import alerts, apps, …` line to also import `live, telemetry` (keep alphabetical order).

In `Orion.__init__` (next to `self._was_minimized = False`) add:
```python
        self._tool_started: dict[str, float] = {}   # skill -> start time (journal and live board durations)
        self._last_heard: dict | None = None        # Google/Whisper texts of the last spoken phrase
        self._thinking_key = "thinking"
        self._delta_text, self._delta_sent = "", 0.0
        self.telemetry: telemetry.Telemetry | None = None
        live.sink = lambda event: self.hud("live", event)
```

In `start()` (the method returning the settings dict), before its `return`, add:
```python
        if self.telemetry is None:  # gauges on the live board — once a second while the window is visible
            self.telemetry = telemetry.Telemetry(lambda gauges: self.hud("setGauges", gauges),
                                                 lambda: self.window is not None and not self._was_minimized)
            self.telemetry.start()
```

`_worker`: change `self._answer(text)` to `self._answer(text, source)`.

Replace `_answer` with:
```python
    def _answer(self, text: str, source: str = "text") -> None:
        self.last_activity = time.time()
        live.begin(text, source, self._last_heard if source == "voice" else None)
        self.hud("addLog", "user", text)
        print(f"[Sir] {text}")
        live.start("understood", "choosing")
        # Time, date, opening programs… — instant and error-free, even before the model is ready.
        reflex = reflexes.respond(text)
        if reflex:
            live.finish("understood", "quick command", {"command": reflex.tool or reflex.action or "time / date"})
            answer = self._run_reflex(text, reflex)
        elif not self.ready:
            live.finish("understood", "the model is not ready", ok=False)
            answer = f"Моля за момент търпение, сър. {self.boot_problem}"
        else:
            answer = self._think(text)  # the brain finishes „understood“ (on_step "route")
        print(f"[Orion] {answer}")
        self._push_reminders()  # it may have added or removed a reminder
        self._speak(answer)
        live.end()
        if reflex and reflex.action == "close" and self.window:
            self.window.destroy()
```

In `_think`, change the brain call and the error branches:
```python
            answer = self.brain.think(text, on_tool=self._log_tool, on_result=self._tool_done,
                                      on_thought=self._thought, on_delta=self._delta, on_step=self._model_step)
        except openai.APIConnectionError:
            live.fail()
            answer = "Изгубих връзка с езиковия модел, сър. Уверете се, че Ollama работи."
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            live.fail()
            answer = f"Възникна техническа неизправност, сър. {e}"
```

Add after `_think`:
```python
    def _model_step(self, kind: str, info: dict) -> None:
        """The brain's progress -> the live board."""
        if kind == "route":
            live.finish("understood", "model", info)
        elif kind == "model_start":
            self._thinking_key = f"thinking-{info['round']}"
            self._delta_text, self._delta_sent = "", 0.0
            live.start("thinking", f"round {info['round'] + 1} · {info['effort']}", info, key=self._thinking_key)
        elif kind == "model_end":
            live.finish("thinking", f"{info['tokens']} tokens · {info['tps']} tok/s", info, key=self._thinking_key)

    def _delta(self, kind: str, text: str) -> None:
        """Streamed pieces of the model's reasoning/answer — at most ~7 updates a second."""
        self._delta_text = (self._delta_text + text)[-600:]
        now = time.monotonic()
        if now - self._delta_sent >= 0.15:
            self._delta_sent = now
            live.update("thinking", kind, {"text": self._delta_text, "kind": kind}, key=self._thinking_key)
```

In `_log_tool`, at the top of the method body add:
```python
        self._tool_started[name] = time.monotonic()
```
and after the existing `self.hud("toolStart", …)` line add:
```python
        live.start("skill", name, {"args": args if isinstance(args, dict) else arguments}, key=name)
```

In `_tool_done`, replace `self.hud("toolDone", name, shown[:200], ok)` with:
```python
        began = self._tool_started.pop(name, None)
        ms = round((time.monotonic() - began) * 1000) if began is not None else None
        self.hud("toolDone", name, shown[:200], ok, ms)
        live.finish("skill", name, {"result": shown[:300]}, ok=ok, key=name)
```

Split `_speak`: rename the existing `def _speak(self, text: str) -> None:` to `def _voice_out(self, text: str) -> None:` (body unchanged) and add above it:
```python
    def _speak(self, text: str) -> None:
        live.start("speaking", text[:140])
        try:
            self._voice_out(text)
        finally:
            live.finish("speaking", text[:140])
```

In `_hear`, replace `text = listener.recognize(audio)` with:
```python
        began = time.monotonic()
        text = listener.recognize(audio)
        google, whisper_text = getattr(listener, "last_heard", (None, None))
        self._last_heard = {"google": google, "whisper": whisper_text, "ms": round((time.monotonic() - began) * 1000)}
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q && python -m pyflakes app.py`
Expected: all pass (`19 passed`), pyflakes silent.

- [ ] **Step 5: Checkpoint** — pytest green; `python web/e2e/run.py` still 29/29 (the window ignores the unknown `hud.live` until Task 6 — `window.hud && hud.live(...)` throws inside `run_js` only if `hud.live` is missing, so add an empty `live() {}` and `setGauges() {}` to `web/src/bridge.js` now and rebuild: `cd web && npm run build`).

---

### Task 6: Window state for the board (`engine/live.js`, store, bridge)

**Files:**
- Create: `web/src/engine/live.js`
- Modify: `web/src/store.js`, `web/src/bridge.js`
- Test: `web/src/engine/live.test.js`, `web/src/bridge.test.js`

**Interfaces:**
- Consumes: event dict from Task 2/5.
- Produces:
  - `applyLiveEvent(live, event, now) -> live` where `live = { traces: Trace[] }` and `Trace = { id, text, source, startedAt, steps: Step[], done: boolean, ok: boolean|null, ms: number|null }`, `Step = { key, phase, label, detail, state: 'run'|'done', ok, ms, t }`; keeps the last 20 traces; unknown or finished traces are ignored.
  - `phaseSummary(trace) -> [{ phase, status: 'idle'|'run'|'done'|'fail', ms, steps }]` for `heard, understood, thinking, skill, speaking`.
  - `nowLine(trace) -> string`, `lastTps(trace) -> number|null`, `formatMs(ms) -> string`.
  - Store fields: `live`, `gauges`, `mood: { kind: 'happy'|'confused'|null, until: number }`, `lastActivity: number`; log entries may have `ms`.
  - `hud.live(event)`, `hud.setGauges(g)`, `hud.toolDone(name, result, ok, ms)`.

- [ ] **Step 1: Write the failing tests**

`web/src/engine/live.test.js`:
```js
import { describe, expect, it } from 'vitest';
import { applyLiveEvent, formatMs, lastTps, nowLine, phaseSummary } from './live.js';

const ev = (o) => ({ trace: 1, detail: null, key: o.key || o.phase, t: 0, ms: null, ok: null, ...o });
const run = (events) => events.reduce((live, e) => applyLiveEvent(live, e, 1000), { traces: [] });

describe('applyLiveEvent', () => {
  it('builds a trace from its events', () => {
    const live = run([
      ev({ phase: 'heard', state: 'end', label: 'Колко е 17 по 23?', detail: { source: 'text' } }),
      ev({ phase: 'understood', state: 'start', label: 'choosing' }),
      ev({ phase: 'understood', state: 'end', label: 'model', ms: 4, ok: true }),
      ev({ phase: 'thinking', state: 'start', label: 'round 1', key: 'thinking-0' }),
      ev({ phase: 'thinking', state: 'update', label: 'reasoning', key: 'thinking-0', detail: { text: 'Трябва да умножа' } }),
    ]);
    const trace = live.traces[0];
    expect(trace.text).toBe('Колко е 17 по 23?');
    expect(trace.steps.map((s) => [s.phase, s.state])).toEqual([['heard', 'done'], ['understood', 'done'], ['thinking', 'run']]);
    expect(nowLine(trace)).toBe('Трябва да умножа');
  });

  it('ignores events of unknown or finished traces and late steps', () => {
    let live = run([ev({ phase: 'heard', state: 'end', label: 'x' }), ev({ phase: 'done', state: 'end', label: 'done', ok: true, ms: 900 })]);
    const before = live;
    live = applyLiveEvent(live, ev({ trace: 99, phase: 'skill', state: 'end', label: 'a' }), 1000);
    live = applyLiveEvent(live, ev({ phase: 'skill', state: 'end', label: 'late' }), 1000);
    expect(live).toBe(before);
  });

  it('keeps only the last 20 traces', () => {
    let live = { traces: [] };
    for (let i = 1; i <= 25; i++) live = applyLiveEvent(live, ev({ trace: i, phase: 'heard', state: 'end', label: `q${i}` }), i);
    expect(live.traces).toHaveLength(20);
    expect(live.traces[0].id).toBe(6);
  });
});

describe('phaseSummary', () => {
  it('reports status and total time per phase', () => {
    const live = run([
      ev({ phase: 'heard', state: 'end', label: 'x', ms: 120, ok: true }),
      ev({ phase: 'skill', state: 'start', label: 'a', key: 'a' }),
      ev({ phase: 'skill', state: 'end', label: 'a', key: 'a', ms: 300, ok: true }),
      ev({ phase: 'skill', state: 'start', label: 'b', key: 'b' }),
      ev({ phase: 'skill', state: 'end', label: 'b', key: 'b', ms: 200, ok: false }),
    ]);
    const byPhase = Object.fromEntries(phaseSummary(live.traces[0]).map((p) => [p.phase, p]));
    expect(byPhase.heard).toMatchObject({ status: 'done', ms: 120 });
    expect(byPhase.skill).toMatchObject({ status: 'fail', ms: 500 });
    expect(byPhase.speaking.status).toBe('idle');
  });
});

describe('helpers', () => {
  it('formats durations', () => {
    expect(formatMs(120)).toBe('120 ms');
    expect(formatMs(1234)).toBe('1.2 s');
  });
  it('reads the speed of the last model round', () => {
    const live = run([
      ev({ phase: 'heard', state: 'end', label: 'x' }),
      ev({ phase: 'thinking', state: 'end', label: 'r', key: 'thinking-0', detail: { tps: 31.5 } }),
    ]);
    expect(lastTps(live.traces[0])).toBe(31.5);
  });
});
```

`web/src/bridge.test.js`:
```js
import { beforeEach, describe, expect, it } from 'vitest';
import { hud } from './bridge.js';
import { store } from './store.js';

const ev = (o) => ({ trace: 7, detail: null, key: o.key || o.phase, t: 0, ms: null, ok: null, ...o });

describe('bridge', () => {
  beforeEach(() => store.set({ live: { traces: [] }, mood: { kind: null, until: 0 }, log: [], gauges: {} }));

  it('hud.live fills the store and a successful skill makes Orion happy', () => {
    hud.live(ev({ phase: 'heard', state: 'end', label: 'Хвърли монета' }));
    hud.live(ev({ phase: 'skill', state: 'start', label: 'flip_coin', key: 'flip_coin' }));
    hud.live(ev({ phase: 'skill', state: 'end', label: 'flip_coin', key: 'flip_coin', ok: true, ms: 3 }));
    hud.live(ev({ phase: 'done', state: 'end', label: 'done', ok: true, ms: 50 }));
    expect(store.get().live.traces[0].done).toBe(true);
    expect(store.get().mood.kind).toBe('happy');
  });

  it('a failed skill makes Orion confused', () => {
    hud.live(ev({ phase: 'heard', state: 'end', label: 'x' }));
    hud.live(ev({ phase: 'skill', state: 'end', label: 'a', key: 'a', ok: false }));
    expect(store.get().mood.kind).toBe('confused');
  });

  it('toolDone writes the duration on the journal entry', () => {
    hud.addLog('tool', 'flip_coin');
    hud.toolDone('flip_coin', 'Падна се ези.', true, 412);
    expect(store.get().log.at(-1).ms).toBe(412);
  });

  it('setGauges stores the values', () => {
    hud.setGauges({ gpu: 20, cpu: 5 });
    expect(store.get().gauges).toEqual({ gpu: 20, cpu: 5 });
  });
});
```

- [ ] **Step 2: Run to see them fail**

Run: `cd web && npm test`
Expected: FAIL — `Failed to resolve import "./live.js"`

- [ ] **Step 3: Implement `web/src/engine/live.js`**

```js
/* The live board's data: every request is a trace of steps (from orion/live.py). Pure functions — the
   store keeps the result, the components only read it. */
export const PIPELINE = ['heard', 'understood', 'thinking', 'skill', 'speaking'];
const KEEP = 20;

export function applyLiveEvent(live, event, now = Date.now()) {
  let traces = live.traces;
  if (event.phase === 'heard' && !traces.some((t) => t.id === event.trace)) {
    const trace = { id: event.trace, text: event.label, source: event.detail?.source || 'text', startedAt: now,
      steps: [], done: false, ok: null, ms: null };
    traces = [...traces, trace].slice(-KEEP);
  }
  const index = traces.findIndex((t) => t.id === event.trace);
  if (index < 0 || traces[index].done) return live;
  const trace = { ...traces[index], steps: [...traces[index].steps] };
  if (event.phase === 'done') {
    Object.assign(trace, { done: true, ok: event.ok, ms: event.ms });
  } else if (event.state === 'start') {
    trace.steps.push({ key: event.key, phase: event.phase, label: event.label, detail: event.detail, state: 'run',
      ok: null, ms: null, t: event.t });
  } else {
    const at = findLast(trace.steps, (s) => s.key === event.key && s.state === 'run');
    if (event.state === 'update') {
      if (at < 0) return live;
      trace.steps[at] = { ...trace.steps[at], label: event.label, detail: { ...trace.steps[at].detail, ...event.detail } };
    } else if (at >= 0) {
      const step = trace.steps[at];
      trace.steps[at] = { ...step, label: event.label || step.label, detail: { ...step.detail, ...event.detail },
        state: 'done', ok: event.ok, ms: event.ms };
    } else {
      trace.steps.push({ key: event.key, phase: event.phase, label: event.label, detail: event.detail, state: 'done',
        ok: event.ok, ms: event.ms, t: event.t });
    }
  }
  const next = [...traces];
  next[index] = trace;
  return { ...live, traces: next };
}

function findLast(items, test) {
  for (let i = items.length - 1; i >= 0; i--) if (test(items[i])) return i;
  return -1;
}

export function phaseSummary(trace) {
  return PIPELINE.map((phase) => {
    const steps = trace.steps.filter((s) => s.phase === phase);
    const status = !steps.length ? 'idle'
      : steps.some((s) => s.state === 'run') ? 'run'
      : steps.some((s) => s.ok === false) ? 'fail' : 'done';
    const times = steps.map((s) => s.ms).filter((ms) => ms != null);
    return { phase, status, ms: times.length ? times.reduce((a, b) => a + b, 0) : null, steps };
  });
}

export function nowLine(trace) {
  if (!trace || trace.done) return '';
  const running = [...trace.steps].reverse().find((s) => s.state === 'run');
  if (!running) return '';
  if (running.phase === 'thinking') return (running.detail?.text || '').replace(/\s+/g, ' ').trim().slice(-140);
  if (running.phase === 'skill') return `skill · ${running.label}`;
  return running.label;
}

export function lastTps(trace) {
  const ends = trace.steps.filter((s) => s.phase === 'thinking' && s.detail?.tps != null);
  return ends.length ? ends.at(-1).detail.tps : null;
}

export const formatMs = (ms) => (ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);
```

- [ ] **Step 4: Store and bridge**

`web/src/store.js` — add to the initial `state` object:
```js
  live: { traces: [] },            // the live board: the last 20 requests and their steps
  gauges: {},                      // { gpu, vramUsed, vramTotal, cpu, ram }
  mood: { kind: null, until: 0 },  // 'happy' | 'confused' for a moment — the eyes show it
  lastActivity: Date.now(),        // sleepy eyes after 10 minutes without anything
```

`web/src/bridge.js` — add the import `import { applyLiveEvent } from './engine/live.js';` and these members to `hud` (replace the placeholder `live() {}` / `setGauges() {}` from Task 5 and the existing `toolDone`):
```js
  live(event) {
    const now = Date.now();
    store.set((s) => {
      const live = applyLiveEvent(s.live, event, now);
      const patch = { live, lastActivity: now };
      if (event.phase === 'skill' && event.state === 'end' && event.ok === false) {
        patch.mood = { kind: 'confused', until: now + 2500 };
      }
      if (event.phase === 'done' && event.ok) {
        const trace = live.traces.find((t) => t.id === event.trace);
        if (trace?.steps.some((st) => st.phase === 'skill' && st.ok)) patch.mood = { kind: 'happy', until: now + 1500 };
      }
      return patch;
    });
  },

  setGauges(gauges) { store.set({ gauges }); },

  toolDone(name, result, ok, ms = null) {
    mind.taskDone(name, result, ok);
    if (ms == null) return;
    store.set((s) => {
      const log = [...s.log];
      for (let i = log.length - 1; i >= 0; i--) {
        if (log[i].kind === 'tool' && log[i].ms == null && log[i].text.startsWith(name)) {
          log[i] = { ...log[i], ms };
          break;
        }
      }
      return { log };
    });
  },
```

- [ ] **Step 5: Run the tests**

Run: `cd web && npm test`
Expected: all pass.

- [ ] **Step 6: Checkpoint** — `npm run build`, `python web/e2e/run.py` 29/29, `python -m pytest -q` green.

---

### Task 7: Expressions, springs, pulse; the network without the reactor

**Files:**
- Create: `web/src/engine/expression.js`, `web/src/engine/spring.js`, `web/src/engine/pulse.js`, `web/src/engine/gaze.js`
- Delete: `web/src/engine/reactor.js`
- Modify: `web/src/engine/mind.js`, `web/src/bridge.js` (import `MODES`), `web/src/components/Stage.jsx` (core layout), `web/src/App.jsx` (activity on keys)
- Test: `web/src/engine/expression.test.js`, `web/src/engine/spring.test.js`, `web/src/engine/pulse.test.js`

**Interfaces:**
- Produces:
  - `COLORS`, `SLEEP_AFTER_MS`, `MODES` (list of valid mode names), `expressionFor({ mode, mood, testActive, idleMs, now }) -> { color: 'holo'|'amber'|'alert'|'test', open, scale, lookX, lookY, tilt, shape: 'box'|'arc', rightEye, spin, sleepy, wave: 'voice'|'think'|'flat' }`
  - `spring(x) -> { x, v, target }`, `stepSpring(s, dt, stiffness = 120, damping = 14) -> number`
  - `pulse = { mode, expr, color: number[3], spin, level, spectrum: Float32Array(24), t, frame(dt) }`
  - `gaze = { x, y, focus: { x, y, until } | null }` — x, y in −1…1 (right/up positive)
  - `mind.attach(canvas, stage, onLayout)` now calls `onLayout({ x, y, core })` where `core` = the old `coreSize`.

- [ ] **Step 1: Write the failing tests**

`web/src/engine/expression.test.js`:
```js
import { describe, expect, it } from 'vitest';
import { expressionFor, SLEEP_AFTER_MS } from './expression.js';

describe('expressionFor', () => {
  it('idle: blue, open, looking ahead', () => {
    expect(expressionFor({ mode: 'idle' })).toMatchObject({ color: 'holo', open: 1, shape: 'box', wave: 'flat', sleepy: false });
  });
  it('listening: amber and larger', () => {
    expect(expressionFor({ mode: 'listening' })).toMatchObject({ color: 'amber', scale: 1.15 });
  });
  it('thinking: squint, look up, fast network, thinking wave', () => {
    expect(expressionFor({ mode: 'thinking' })).toMatchObject({ open: 0.55, lookY: 0.3, spin: 2.6, wave: 'think' });
  });
  it('speaking: the voice wave', () => {
    expect(expressionFor({ mode: 'speaking' }).wave).toBe('voice');
  });
  it('happy mood: arcs while it lasts', () => {
    expect(expressionFor({ mode: 'idle', mood: { kind: 'happy', until: 10 }, now: 5 }).shape).toBe('arc');
    expect(expressionFor({ mode: 'idle', mood: { kind: 'happy', until: 10 }, now: 11 }).shape).toBe('box');
  });
  it('confused or offline: red, tilted, smaller right eye', () => {
    for (const e of [expressionFor({ mode: 'idle', mood: { kind: 'confused', until: 10 }, now: 5 }), expressionFor({ mode: 'offline' })]) {
      expect(e).toMatchObject({ color: 'alert', tilt: 0.18, rightEye: 0.65 });
    }
  });
  it('test mode: green unless listening', () => {
    expect(expressionFor({ mode: 'idle', testActive: true }).color).toBe('test');
    expect(expressionFor({ mode: 'listening', testActive: true }).color).toBe('amber');
  });
  it('sleepy after 10 minutes of quiet', () => {
    expect(expressionFor({ mode: 'idle', idleMs: SLEEP_AFTER_MS + 1 })).toMatchObject({ sleepy: true, open: 0.35 });
    expect(expressionFor({ mode: 'thinking', idleMs: SLEEP_AFTER_MS + 1 }).sleepy).toBe(false);
  });
});
```

`web/src/engine/spring.test.js`:
```js
import { describe, expect, it } from 'vitest';
import { spring, stepSpring } from './spring.js';

describe('spring', () => {
  it('settles on the target within a second without wild overshoot', () => {
    const s = spring(0);
    s.target = 1;
    let peak = 0;
    for (let i = 0; i < 60; i++) peak = Math.max(peak, stepSpring(s, 1 / 60));
    expect(Math.abs(s.x - 1)).toBeLessThan(0.05);
    expect(peak).toBeLessThan(1.25);
  });
});
```

`web/src/engine/pulse.test.js`:
```js
import { describe, expect, it } from 'vitest';
import { store } from '../store.js';
import { COLORS } from './expression.js';
import { pulse } from './pulse.js';

describe('pulse', () => {
  it('moves the colour towards the state colour', () => {
    store.set({ mode: 'listening', mood: { kind: null, until: 0 }, test: null, lastActivity: Date.now() });
    for (let i = 0; i < 60; i++) pulse.frame(1 / 30);
    pulse.color.forEach((c, i) => expect(Math.abs(c - COLORS.amber[i])).toBeLessThan(3));
    expect(pulse.expr.color).toBe('amber');
  });
});
```

- [ ] **Step 2: Run to see them fail**

Run: `cd web && npm test`
Expected: FAIL — unresolved imports.

- [ ] **Step 3: Implement the engine modules**

`web/src/engine/expression.js`:
```js
/* What the eyes should look like for Orion's state — a pure function, so every state is testable. */
export const COLORS = { holo: [127, 219, 255], amber: [255, 181, 71], alert: [255, 90, 78], test: [140, 227, 176] };
export const MODES = ['boot', 'idle', 'standby', 'calibrating', 'listening', 'thinking', 'speaking', 'offline', 'approval'];
export const SLEEP_AFTER_MS = 10 * 60 * 1000;

export function expressionFor({ mode = 'idle', mood = null, testActive = false, idleMs = 0, now = 0 } = {}) {
  const e = { color: 'holo', open: 1, scale: 1, lookX: 0, lookY: 0, tilt: 0, shape: 'box', rightEye: 1,
    spin: 0.18, sleepy: false, wave: 'flat' };
  const moodKind = mood && now < mood.until ? mood.kind : null;
  if (testActive) e.color = 'test';
  if (['listening', 'standby', 'calibrating', 'approval'].includes(mode)) e.color = 'amber';
  if (mode === 'listening' || mode === 'calibrating') Object.assign(e, { scale: 1.15, spin: 0.45 });
  if (mode === 'thinking' || mode === 'boot') {
    Object.assign(e, { open: 0.55, lookX: 0.3, lookY: 0.3, spin: mode === 'boot' ? 0.9 : 2.6, wave: 'think' });
  }
  if (mode === 'speaking') Object.assign(e, { spin: 0.3, wave: 'voice' });
  if (moodKind === 'happy') e.shape = 'arc';
  if (moodKind === 'confused' || mode === 'offline') Object.assign(e, { color: 'alert', tilt: 0.18, rightEye: 0.65, spin: 0.05 });
  if (mode === 'idle' && !moodKind && idleMs > SLEEP_AFTER_MS) Object.assign(e, { sleepy: true, open: 0.35, lookY: -0.15, spin: 0.06 });
  return e;
}
```

`web/src/engine/spring.js`:
```js
/* Springs: a value follows its target with velocity — soft, natural movement instead of jumps. */
export const spring = (x = 0) => ({ x, v: 0, target: x });

export function stepSpring(s, dt, stiffness = 120, damping = 14) {
  const a = stiffness * (s.target - s.x) - damping * s.v;
  s.v += a * dt;
  s.x += s.v * dt;
  return s.x;
}
```

`web/src/engine/gaze.js`:
```js
/* Where the eyes look: the mouse (x, y in −1…1, right/up positive) or, for a moment, a skill bubble. */
export const gaze = { x: 0, y: 0, focus: null };
```

`web/src/engine/pulse.js`:
```js
/* The heartbeat shared by the network and the eyes: Orion's state colour, spin and the voice level.
   Updated once per frame by engine/mind.js. */
import { store } from '../store.js';
import { reduceMotion } from '../util.js';
import { COLORS, expressionFor } from './expression.js';
import { voice } from './voice.js';

export const pulse = {
  mode: 'boot',
  expr: expressionFor({ mode: 'boot' }),
  color: [...COLORS.holo],
  spin: 0.9,
  level: 0,
  spectrum: new Float32Array(24),
  t: 0,

  frame(dt) {
    const s = store.get();
    const now = Date.now();
    this.mode = s.mode;
    this.expr = expressionFor({ mode: s.mode, mood: s.mood, testActive: Boolean(s.test), idleMs: now - s.lastActivity, now });
    this.t += dt;
    const ease = (k) => Math.min(1, dt * k);
    const target = COLORS[this.expr.color];
    for (let i = 0; i < 3; i++) this.color[i] += (target[i] - this.color[i]) * ease(4);
    this.spin += (this.expr.spin - this.spin) * ease(3);
    if (voice.analyser && voice.playing) {
      voice.analyser.getByteFrequencyData(voice.bins);
      let sum = 0;
      for (let i = 0; i < 24; i++) {
        const v = Math.min(1, (voice.bins[2 + Math.round(i * 1.6)] / 255) * (0.8 + i / 14));
        this.spectrum[i] += (v - this.spectrum[i]) * ease(18);
        sum += v;
      }
      this.level += (Math.min(1, (sum / 24) * 2.2) - this.level) * ease(20);
    } else {
      for (let i = 0; i < 24; i++) this.spectrum[i] *= 1 - ease(6);
      const breathe = Math.sin(this.t * 1.3) * 0.06 * (reduceMotion ? 0.15 : 1);
      this.level += (0.3 + breathe - this.level) * ease(4);
    }
  },
};
```

- [ ] **Step 4: Rewire `mind.js` and the rest**

In `web/src/engine/mind.js`:
- Replace `import { MODES, reactor } from './reactor.js';` with `import { gaze } from './gaze.js';` and `import { pulse } from './pulse.js';` and add `import { store } from '../store.js';`.
- `resize()`: delete `reactor.resize(this.coreSize);`; change the reserve for the label/pipeline/subtitles: `this.R = Math.max(90, Math.min(this.w * 0.27, (this.h - 210) * 0.4));` and `this.cy = Math.max(this.R * 1.05, (this.h - 220) / 2 + 22);`; replace the `onLayout` call with `this.onLayout?.({ x: this.cx, y: this.cy, core: this.coreSize });`.
- `frame()`: `reactor.frame(dt)` → `pulse.frame(dt)`; `reactor.spin` → `pulse.spin`.
- `update()`: replace the first two lines with `const mode = pulse.mode;` and `const thinking = mode === 'thinking';`; `state === MODES.listening || state === MODES.calibrating` → `mode === 'listening' || mode === 'calibrating'`; `state === MODES.standby` → `mode === 'standby'`; `reactor.level` → `pulse.level`.
- `draw()`: `reactor.color` → `pulse.color`. Around steps 1–2 (neuron cloud and sparks) cut a hole for the eyes:
```js
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, this.w, this.h);
    ctx.arc(this.cx, this.cy, this.coreSize * 0.7, 0, TAU);
    ctx.clip('evenodd');  // the eyes live in this hole (components/Eyes.jsx)
```
  before `// 1. The neuron cloud` and `ctx.restore();` right after the sparks block. Delete the `ctx.drawImage(reactor.canvas, …)` line. In `drawRings`, keep only the outer ring: `const rings = [{ r: 1.2, tilt: [0.06, 0, 0], speed: 0.05, dash: 0, ticks: true }];` and `reactor.spin` → `pulse.spin`. In the links block, `this.coreEdge(p, 0.34)` → `this.coreEdge(p, 0.7)` (twice).
- `bindPointer()` `move`: after computing `mx, my`, add
```js
      gaze.x = Math.max(-1, Math.min(1, (mx - this.cx) / (this.w / 2)));
      gaze.y = Math.max(-1, Math.min(1, -(my - this.cy) / (this.h / 2)));
      const now = Date.now();
      if (now - store.get().lastActivity > 1000) store.set({ lastActivity: now });  // wakes sleepy eyes
```
  and in `up`, the core test radius `this.coreSize * 0.32` → `this.coreSize * 0.5` (twice: `move` cursor and `up`).
- `taskStart()`: after the node is chosen add
```js
    const p = this.proj.get(node);
    if (p) gaze.focus = { x: (p.x - this.cx) / (this.w / 2), y: -(p.y - this.cy) / (this.h / 2), until: Date.now() + 1000 };
```

Delete `web/src/engine/reactor.js`. In `web/src/bridge.js` replace `import { MODES } from './engine/reactor.js';` with `import { MODES } from './engine/expression.js';` and in `setState` change `if (!MODES[mode]) return;` to `if (!MODES.includes(mode)) return;`.

`web/src/components/Stage.jsx` — the core button uses the new layout:
```jsx
        style={core ? { width: core.core * 0.9, height: core.core * 0.9, left: core.x, top: core.y } : undefined}
```

`web/src/App.jsx` — inside the `keydown` handler, first line: `store.set({ lastActivity: Date.now() });`.

- [ ] **Step 5: Run everything**

Run: `cd web && npm test && npm run build && cd .. && python web/e2e/run.py`
Expected: Vitest all pass; build ok; 29/29 (the centre is empty until Task 8 — expected).

- [ ] **Step 6: Checkpoint** — the three suites green.

---

### Task 8: The eyes (3D with bloom, 2D fallback)

**Files:**
- Create: `web/src/engine/eyesRig.js`, `web/src/components/Eyes.jsx`, `web/src/components/Eyes3D.jsx`, `web/src/components/Eyes2D.jsx`
- Modify: `web/src/components/Stage.jsx` (renders `<Eyes>`), `web/src/styles.css`, `web/package.json` (dependencies), `web/vite.config.js` (single bundle)
- Modify: `web/e2e/interact.js` (eye checks)
- Test: `web/src/engine/eyesRig.test.js`, `web/src/components/Eyes.test.jsx`

**Interfaces:**
- Consumes: `expressionFor` output, `pulse`, `gaze`, `stepSpring` (Task 7).
- Produces: `createRig(random = Math.random) -> { step(dt, expr, gaze, spectrum, now, t) -> Pose }`, `Pose = { lookX, lookY, open, scale, tilt, right, shape, bars: number[25] }`; `<Eyes layout={{ x, y, core }} />`; `webglAvailable() -> boolean`.

- [ ] **Step 1: Install the 3D packages**

```bash
cd web && npm install --no-fund --no-audit three@0.186.1 @react-three/fiber@9.8.1 @react-three/postprocessing@3.1.3 postprocessing motion@14.0.0
```
(`postprocessing` at the version npm resolves for the `^6.36.0` peer.) In `web/vite.config.js` → `build.rollupOptions.output` add `inlineDynamicImports: true` (IIFE must be one file).

- [ ] **Step 2: Write the failing tests**

`web/src/engine/eyesRig.test.js`:
```js
import { describe, expect, it } from 'vitest';
import { expressionFor } from './expression.js';
import { createRig } from './eyesRig.js';

const still = { x: 0, y: 0, focus: null };
const quiet = new Float32Array(24);
const run = (rig, expr, seconds, gaze = still, spectrum = quiet) => {
  let pose;
  for (let i = 0; i < seconds * 30; i++) pose = rig.step(1 / 30, expr, gaze, spectrum, i * 33, i / 30);
  return pose;
};

describe('eyes rig', () => {
  it('blinks every few seconds', () => {
    const rig = createRig(() => 0.5);
    let closed = 0;
    for (let i = 0; i < 30 * 8; i++) if (rig.step(1 / 30, expressionFor({ mode: 'idle' }), still, quiet, i * 33, i / 30).open < 0.3) closed++;
    expect(closed).toBeGreaterThan(0);
  });
  it('squints while thinking', () => {
    const pose = run(createRig(() => 0.99), expressionFor({ mode: 'thinking' }), 1.5);
    expect(pose.open).toBeGreaterThan(0.45);
    expect(pose.open).toBeLessThan(0.7);
  });
  it('follows the mouse', () => {
    const pose = run(createRig(() => 0.99), expressionFor({ mode: 'idle' }), 1.5, { x: 1, y: 0, focus: null });
    expect(pose.lookX).toBeGreaterThan(0.25);
  });
  it('a skill bubble wins over the mouse while it lasts', () => {
    const pose = run(createRig(() => 0.99), expressionFor({ mode: 'idle' }), 0.8, { x: 1, y: 0, focus: { x: -1, y: 0, until: 1e12 } });
    expect(pose.lookX).toBeLessThan(-0.2);
  });
  it('the voice wave only while speaking', () => {
    const loud = new Float32Array(24).fill(0.8);
    expect(Math.max(...run(createRig(), expressionFor({ mode: 'speaking' }), 0.5, still, loud).bars)).toBeGreaterThan(0.5);
    expect(Math.max(...run(createRig(), expressionFor({ mode: 'idle' }), 0.5, still, loud).bars)).toBeLessThan(0.1);
  });
});
```

`web/src/components/Eyes.test.jsx`:
```jsx
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Eyes } from './Eyes.jsx';

describe('Eyes', () => {
  it('falls back to 2D eyes without WebGL (jsdom has none)', () => {
    const { container } = render(<Eyes layout={{ x: 200, y: 150, core: 120 }} />);
    expect(container.querySelector('.eyes--2d canvas')).not.toBeNull();
  });
  it('waits for the layout', () => {
    const { container } = render(<Eyes layout={null} />);
    expect(container.innerHTML).toBe('');
  });
});
```

- [ ] **Step 3: Run to see them fail**

Run: `cd web && npm test`
Expected: FAIL — unresolved imports.

- [ ] **Step 4: Implement the rig**

`web/src/engine/eyesRig.js`:
```js
/* The eyes' motion, shared by the 3D and the 2D eyes: springs towards the expression, blinking, the
   gaze (mouse or a skill bubble) and the wave under the eyes. */
import { spring, stepSpring } from './spring.js';

export function createRig(random = Math.random) {
  const s = { lookX: spring(0), lookY: spring(0), open: spring(1), scale: spring(1), tilt: spring(0), right: spring(1) };
  let nextBlink = 2 + random() * 3;
  let blinking = 0;
  return {
    step(dt, expr, gaze, spectrum, now, t) {
      const focus = gaze.focus && now < gaze.focus.until ? gaze.focus : null;
      const drift = expr.wave === 'flat' && !expr.sleepy ? Math.sin(t * 0.7) * 0.12 : 0;
      s.lookX.target = (focus ? focus.x : gaze.x) * 0.35 + expr.lookX + drift;
      s.lookY.target = (focus ? focus.y : gaze.y) * 0.25 + expr.lookY;
      nextBlink -= dt;
      if (nextBlink <= 0) {
        blinking = 0.14;
        nextBlink = 2 + random() * 3;
      }
      s.open.target = blinking > 0 ? 0.05 : expr.open;
      blinking -= dt;
      s.scale.target = expr.scale;
      s.tilt.target = expr.tilt;
      s.right.target = expr.rightEye;
      stepSpring(s.open, dt, 600, 40);  // eyelids are quick
      for (const key of ['lookX', 'lookY', 'scale', 'tilt', 'right']) stepSpring(s[key], dt);
      const bars = Array.from({ length: 25 }, (_, i) => {
        const k = Math.abs(i - 12) / 12;
        if (expr.wave === 'voice') return Math.max(0.05, (spectrum[Math.min(23, Math.round(k * 23))] || 0) * 1.6 * (1 - k * 0.6));
        if (expr.wave === 'think') return 0.05 + 0.25 * Math.max(0, Math.sin(t * 6 - i * 0.5));
        return 0.05;
      });
      return { lookX: s.lookX.x, lookY: s.lookY.x, open: Math.max(0.04, s.open.x), scale: s.scale.x,
        tilt: s.tilt.x, right: s.right.x, shape: expr.shape, bars };
    },
  };
}
```

- [ ] **Step 5: Implement the components**

`web/src/components/Eyes3D.jsx`:
```jsx
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Bloom, EffectComposer } from '@react-three/postprocessing';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { createRig } from '../engine/eyesRig.js';
import { gaze } from '../engine/gaze.js';
import { pulse } from '../engine/pulse.js';

const FPS = 30;

// Renders on demand, 30 times a second at most and never while the window is hidden.
function Ticker() {
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => {
    const timer = setInterval(() => { if (!document.hidden) invalidate(); }, 1000 / FPS);
    return () => clearInterval(timer);
  }, [invalidate]);
  return null;
}

function Face() {
  const rig = useMemo(() => createRig(), []);
  const material = useMemo(() => new THREE.MeshBasicMaterial({ color: '#7FDBFF' }), []);
  const box = useMemo(() => new RoundedBoxGeometry(1.25, 1.5, 0.4, 6, 0.42), []);
  const arc = useMemo(() => new THREE.TorusGeometry(0.62, 0.16, 12, 40, Math.PI), []);
  const bar = useMemo(() => new THREE.BoxGeometry(0.12, 1, 0.12), []);
  const head = useRef();
  const eyes = useRef([]);
  const arcs = useRef([]);
  const bars = useRef([]);
  const last = useRef(performance.now());
  useFrame(() => {
    const now = performance.now();
    const dt = Math.min(0.1, (now - last.current) / 1000);
    last.current = now;
    const pose = rig.step(dt, pulse.expr, gaze, pulse.spectrum, Date.now(), pulse.t);
    const [r, g, b] = pulse.color;
    material.color.setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace).multiplyScalar(0.8);
    head.current.position.set(pose.lookX, pose.lookY, 0);
    head.current.rotation.set(-pose.lookY * 0.4, pose.lookX * 0.5, pose.tilt);
    head.current.scale.setScalar(pose.scale);
    const happy = pose.shape === 'arc';
    eyes.current.forEach((eye, i) => {
      eye.visible = !happy;
      eye.scale.set(1, pose.open * (i ? pose.right : 1), 1);
    });
    arcs.current.forEach((a) => { a.visible = happy; });
    bars.current.forEach((b, i) => { b.scale.y = pose.bars[i]; });
  });
  return (
    <group ref={head}>
      {[-1.25, 1.25].map((x, i) => (
        <mesh key={`eye${x}`} ref={(el) => { eyes.current[i] = el; }} geometry={box} material={material} position={[x, 0, 0]} />
      ))}
      {[-1.25, 1.25].map((x, i) => (
        <mesh key={`arc${x}`} ref={(el) => { arcs.current[i] = el; }} geometry={arc} material={material}
              position={[x, -0.25, 0]} visible={false} />
      ))}
      {Array.from({ length: 25 }, (_, i) => (
        <mesh key={i} ref={(el) => { bars.current[i] = el; }} geometry={bar} material={material} position={[(i - 12) * 0.2, -1.9, 0]} />
      ))}
    </group>
  );
}

export default function Eyes3D() {
  return (
    <Canvas frameloop="demand" dpr={[1, 1.5]} camera={{ position: [0, 0, 9], fov: 40 }}
            gl={{ antialias: true, powerPreference: 'low-power', alpha: false }}
            onCreated={({ gl }) => gl.setClearColor('#04090F')}>
      <Ticker />
      <Face />
      <EffectComposer>
        <Bloom intensity={0.7} luminanceThreshold={0.12} mipmapBlur radius={0.32} />
      </EffectComposer>
    </Canvas>
  );
}
```

`web/src/components/Eyes2D.jsx`:
```jsx
import { useEffect, useRef } from 'react';
import { createRig } from '../engine/eyesRig.js';
import { gaze } from '../engine/gaze.js';
import { pulse } from '../engine/pulse.js';

// The same eyes on a 2D canvas — when WebGL is missing or the 3D eyes fail.
export function Eyes2D() {
  const canvas = useRef(null);
  useEffect(() => {
    const el = canvas.current;
    const ctx = el.getContext('2d');
    if (!ctx) return undefined;
    const rig = createRig();
    let last = performance.now();
    const draw = () => {
      if (document.hidden) return;
      const now = performance.now();
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = el.clientWidth, h = el.clientHeight;
      if (el.width !== Math.round(w * dpr)) { el.width = Math.round(w * dpr); el.height = Math.round(h * dpr); }
      const pose = rig.step(dt, pulse.expr, gaze, pulse.spectrum, Date.now(), pulse.t);
      const [r, g, b] = pulse.color.map(Math.round);
      const u = w / 6.5;  // one 3D unit in pixels (the 3D camera sees ~6.5 units)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#04090F';
      ctx.fillRect(0, 0, w, h);
      ctx.translate(w / 2 + pose.lookX * u, h / 2 - pose.lookY * u);
      ctx.rotate(pose.tilt);
      ctx.scale(pose.scale, pose.scale);
      ctx.shadowColor = `rgba(${r},${g},${b},0.9)`;
      ctx.shadowBlur = 24;
      ctx.fillStyle = ctx.strokeStyle = `rgb(${r},${g},${b})`;
      for (const [side, factor] of [[-1, 1], [1, pose.right]]) {
        const x = side * 1.25 * u;
        if (pose.shape === 'arc') {
          ctx.lineWidth = 0.32 * u;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.arc(x, 0.25 * u, 0.62 * u, Math.PI * 1.1, Math.PI * 1.9);
          ctx.stroke();
        } else {
          const ew = 1.25 * u, eh = Math.max(2, 1.5 * u * pose.open * factor);
          ctx.beginPath();
          ctx.roundRect(x - ew / 2, -eh / 2, ew, eh, Math.min(0.42 * u, eh / 2));
          ctx.fill();
        }
      }
      ctx.shadowBlur = 10;
      pose.bars.forEach((v, i) => {
        const bh = Math.max(2, v * u);
        ctx.fillRect((i - 12) * 0.2 * u - 0.06 * u, 1.9 * u - bh / 2, 0.12 * u, bh);
      });
    };
    const timer = setInterval(draw, 1000 / 30);
    return () => clearInterval(timer);
  }, []);
  return <canvas ref={canvas} />;
}
```

`web/src/components/Eyes.jsx`:
```jsx
import { Component, useState } from 'react';
import { api } from '../util.js';
import { Eyes2D } from './Eyes2D.jsx';
import Eyes3D from './Eyes3D.jsx';

export function webglAvailable() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch {
    return false;
  }
}

// A 3D failure (lost context, driver) must never leave the centre empty — 2D eyes take over.
class Fallback extends Component {
  state = { failed: false };

  static getDerivedStateFromError() { return { failed: true }; }

  componentDidCatch(error) { api()?.report_error(`3D eyes: ${error.message}`); }

  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

// Orion's eyes in the centre of the network. The 2D network canvas lies on top and leaves a hole here.
export function Eyes({ layout }) {
  const [three] = useState(webglAvailable);
  if (!layout) return null;
  const size = layout.core * 1.9;
  const style = { left: layout.x - size / 2, top: layout.y - size / 2, width: size, height: size };
  const flat = <div className="eyes eyes--2d" style={style} aria-hidden="true"><Eyes2D /></div>;
  if (!three) return flat;
  return (
    <Fallback fallback={flat}>
      <div className="eyes eyes--3d" style={style} aria-hidden="true"><Eyes3D /></div>
    </Fallback>
  );
}
```

`web/src/components/Stage.jsx`: import `{ Eyes }` from `./Eyes.jsx`; render `<Eyes layout={core} />` as the first child of `<section className="stage">` (before `<canvas className="mind" …>`).

`web/src/styles.css` — add after the `.mind:active` rule:
```css
/* The eyes sit under the network canvas; their edge fades into the background. */
.eyes {
  position: absolute;
  pointer-events: none;
  -webkit-mask-image: radial-gradient(circle, #000 52%, transparent 70%);
  mask-image: radial-gradient(circle, #000 52%, transparent 70%);
}
.eyes canvas { display: block; width: 100% !important; height: 100% !important; }
```

- [ ] **Step 6: Run the tests and the build**

Run: `cd web && npm test && npm run build`
Expected: all pass; `ui/assets/orion.js` is one file (no extra chunks in `ui/assets/`).

- [ ] **Step 7: Browser checks for the eyes**

In `web/e2e/interact.js`, before the final `const pre = …` line, add:
```js
  check('the eyes are drawn in the centre', Boolean(document.querySelector('.eyes canvas')));
  const eyesBox = document.querySelector('.eyes').getBoundingClientRect();
  const stageBox = document.querySelector('.stage').getBoundingClientRect();
  check('the eyes are inside the stage', eyesBox.left >= stageBox.left - 1 && eyesBox.right <= stageBox.right + 1);
```

Run: `python web/e2e/run.py`
Expected: `passed 31, failed 0` (with `--disable-gpu` this exercises the 2D fallback or SwiftShader).

- [ ] **Step 8: Checkpoint** — all suites green.

---

### Task 9: The live board (pipeline, step details, gauges, jobs, journal durations)

**Files:**
- Create: `web/src/components/Pipeline.jsx`, `web/src/components/StepDetails.jsx`, `web/src/components/Gauges.jsx`, `web/src/components/Jobs.jsx`
- Modify: `web/src/components/Stage.jsx` (pipeline under the eyes), `web/src/components/TopBar.jsx` (gauges and jobs replace the two chips), `web/src/components/Journal.jsx` (duration badge), `web/src/styles.css`
- Modify: `web/e2e/interact.js` (board checks)
- Test: `web/src/components/Pipeline.test.jsx`, `web/src/components/Gauges.test.jsx`, `web/src/components/Jobs.test.jsx`

**Interfaces:**
- Consumes: `phaseSummary`, `nowLine`, `lastTps`, `formatMs` (Task 6); store `live`, `gauges`, `test`, `reels`, `approval`, `log[].ms`.

- [ ] **Step 1: Write the failing tests**

`web/src/components/Pipeline.test.jsx`:
```jsx
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { store } from '../store.js';
import { Pipeline } from './Pipeline.jsx';

const trace = {
  id: 1, text: 'Ще вали ли утре?', source: 'text', startedAt: 0, done: false, ok: null, ms: null,
  steps: [
    { key: 'heard', phase: 'heard', label: 'Ще вали ли утре?', detail: { source: 'text' }, state: 'done', ok: true, ms: null, t: 0 },
    { key: 'understood', phase: 'understood', label: 'quick command', detail: { command: 'will_it_rain' }, state: 'done', ok: true, ms: 3, t: 0 },
    { key: 'will_it_rain', phase: 'skill', label: 'will_it_rain', detail: { args: { day: 'утре' } }, state: 'run', ok: null, ms: null, t: 0.01 },
  ],
};

describe('Pipeline', () => {
  beforeEach(() => store.set({ live: { traces: [trace] } }));

  it('shows the five steps and highlights the running one', () => {
    render(<Pipeline />);
    const steps = screen.getAllByRole('button');
    expect(steps.map((b) => b.dataset.phase)).toEqual(['heard', 'understood', 'thinking', 'skill', 'speaking']);
    expect(steps[3].className).toContain('is-run');
    expect(steps[1].textContent).toContain('3 ms');
    expect(screen.getByText('skill · will_it_rain')).toBeTruthy();
  });

  it('opens the details of a step', () => {
    render(<Pipeline />);
    fireEvent.click(screen.getAllByRole('button')[1]);
    expect(screen.getByRole('dialog').textContent).toContain('will_it_rain');
  });

  it('shows nothing before the first request', () => {
    store.set({ live: { traces: [] } });
    const { container } = render(<Pipeline />);
    expect(container.innerHTML).toBe('');
  });
});
```

`web/src/components/Gauges.test.jsx`:
```jsx
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { store } from '../store.js';
import { Gauges } from './Gauges.jsx';

describe('Gauges', () => {
  it('shows the values it has and hides the missing ones', () => {
    store.set({ gauges: { cpu: 12, ram: 48 }, live: { traces: [] } });
    const { container } = render(<Gauges />);
    expect(container.textContent).toContain('CPU 12%');
    expect(container.textContent).toContain('RAM 48%');
    expect(container.textContent).not.toContain('GPU');
  });

  it('shows GPU, video memory and the last answer', () => {
    store.set({ gauges: { gpu: 22, vramUsed: 8192, vramTotal: 10240, cpu: 5, ram: 40 }, live: { traces: [{
      id: 1, done: true, ok: true, ms: 2100, steps: [{ phase: 'thinking', state: 'done', detail: { tps: 34.2 } }] }] } });
    const { container } = render(<Gauges />);
    expect(container.textContent).toContain('GPU 22%');
    expect(container.textContent).toContain('VRAM 8.0/10 GB');
    expect(container.textContent).toContain('34.2 tok/s');
    expect(container.textContent).toContain('last 2.1 s');
  });
});
```

`web/src/components/Jobs.test.jsx`:
```jsx
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { store } from '../store.js';
import { Jobs } from './Jobs.jsx';

describe('Jobs', () => {
  it('lists the background work', () => {
    store.set({ test: 'test · round 2', reels: 'reels · cutting reel 1/3', approval: { confirm: false } });
    const { container } = render(<Jobs />);
    expect(container.textContent).toContain('test · round 2');
    expect(container.textContent).toContain('reels · cutting reel 1/3');
    expect(container.textContent).toContain('waiting for your approval');
  });
  it('is empty when nothing runs', () => {
    store.set({ test: null, reels: null, approval: null });
    const { container } = render(<Jobs />);
    expect(container.innerHTML).toBe('');
  });
});
```

- [ ] **Step 2: Run to see them fail**

Run: `cd web && npm test`
Expected: FAIL — unresolved imports.

- [ ] **Step 3: Implement the components**

`web/src/components/StepDetails.jsx`:
```jsx
import { motion } from 'motion/react';
import { formatMs } from '../engine/live.js';

const show = (value) => {
  if (value == null) return '—';
  if (typeof value === 'string') return value.length > 600 ? `${value.slice(0, 600)}…` : value;
  if (Array.isArray(value)) return value.join(', ') || '—';
  return JSON.stringify(value);
};

// What exactly happened in one step: every value the Python side sent, readable.
export function StepDetails({ phase, steps, onClose }) {
  return (
    <motion.div className="step-details" role="dialog" aria-label={`${phase} details`}
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.16 }}>
      <button type="button" className="step-details-close" aria-label="Close" onClick={onClose}>×</button>
      {steps.length === 0 && <p className="step-details-empty">Nothing yet in this step.</p>}
      {steps.map((step, i) => (
        <section key={`${step.key}-${i}`}>
          <h4>{step.label}{step.ms != null && <small>{formatMs(step.ms)}</small>}{step.ok === false && <em>failed</em>}</h4>
          {step.detail && (
            <dl>
              {Object.entries(step.detail).map(([key, value]) => (
                <div key={key}><dt>{key}</dt><dd>{show(value)}</dd></div>
              ))}
            </dl>
          )}
        </section>
      ))}
    </motion.div>
  );
}
```

`web/src/components/Pipeline.jsx`:
```jsx
import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';
import { formatMs, nowLine, phaseSummary } from '../engine/live.js';
import { useStore } from '../store.js';
import { StepDetails } from './StepDetails.jsx';

// heard → understood → thinking → skill → speaking, under the eyes. Click a step for its details.
export function Pipeline() {
  const traces = useStore((s) => s.live.traces);
  const [open, setOpen] = useState(null);
  const trace = traces.at(-1);
  if (!trace) return null;
  const phases = phaseSummary(trace);
  const now = nowLine(trace);
  return (
    <div className="pipeline">
      <ol className="pipe-steps">
        {phases.map((p, i) => (
          <li key={p.phase}>
            {i > 0 && <span className="pipe-arrow" aria-hidden="true">→</span>}
            <motion.button type="button" data-phase={p.phase} className={`pipe-step is-${p.status}`}
                           aria-expanded={open === p.phase} onClick={() => setOpen(open === p.phase ? null : p.phase)}
                           animate={{ scale: p.status === 'run' ? 1.06 : 1 }}
                           transition={{ type: 'spring', stiffness: 420, damping: 24 }}>
              {p.phase}
              {p.ms != null && <small>{formatMs(p.ms)}</small>}
            </motion.button>
          </li>
        ))}
      </ol>
      <p className="pipe-now" aria-live="polite">{now}</p>
      <AnimatePresence>
        {open && <StepDetails key={open} phase={open} steps={phases.find((p) => p.phase === open).steps} onClose={() => setOpen(null)} />}
      </AnimatePresence>
    </div>
  );
}
```

`web/src/components/Gauges.jsx`:
```jsx
import { formatMs, lastTps } from '../engine/live.js';
import { useStore } from '../store.js';

// Live gauges in the top bar (from orion/telemetry.py) and the speed and time of the last answer.
export function Gauges() {
  const g = useStore((s) => s.gauges);
  const traces = useStore((s) => s.live.traces);
  const last = [...traces].reverse().find((t) => t.done);
  const items = [];
  if (g.gpu != null) items.push(['GPU', `${g.gpu}%`]);
  if (g.vramUsed != null && g.vramTotal) items.push(['VRAM', `${(g.vramUsed / 1024).toFixed(1)}/${Math.round(g.vramTotal / 1024)} GB`]);
  if (g.cpu != null) items.push(['CPU', `${g.cpu}%`]);
  if (g.ram != null) items.push(['RAM', `${g.ram}%`]);
  const tps = last ? lastTps(last) : null;
  if (tps != null) items.push(['speed', `${tps} tok/s`]);
  if (last?.ms != null) items.push(['last', formatMs(last.ms)]);
  if (!items.length) return null;
  return (
    <span className="gauges pywebview-drag-region">
      {items.map(([name, value]) => <span key={name} className="gauge"><i>{name}</i> {value}</span>)}
    </span>
  );
}
```

`web/src/components/Jobs.jsx`:
```jsx
import { useStore } from '../store.js';

// Background work — test mode, reels, a proposal waiting for approval — always in sight.
export function Jobs() {
  const test = useStore((s) => s.test);
  const reels = useStore((s) => s.reels);
  const approval = useStore((s) => s.approval);
  const jobs = [test && ['test', test], reels && ['reels', reels], approval && ['approval', 'waiting for your approval']]
    .filter(Boolean);
  if (!jobs.length) return null;
  return (
    <span className="jobs pywebview-drag-region">
      {jobs.map(([kind, text]) => <span key={kind} className={`tele-chip tele-chip--${kind}`}>{text}</span>)}
    </span>
  );
}
```

`web/src/components/TopBar.jsx`: import `{ Gauges }` and `{ Jobs }`; replace the two chip lines (`{test && …}` and `{reels && …}`) with `<Jobs />`, and add `<Gauges />` right before `<Clock />`; remove the now unused `test`/`reels` selectors.

`web/src/components/Stage.jsx`: import `{ Pipeline }`; render `<Pipeline />` right before `<p className="state-label">`.

`web/src/components/Journal.jsx`: import `formatMs` from `../engine/live.js`; in `Entry`, render after `<b>…</b>`: `{entry.ms != null && <small className="entry-ms">{formatMs(entry.ms)}</small>}` and destructure `ms` is not needed (read `entry.ms`).

`web/src/styles.css` — append:
```css
/* --- Live board ---------------------------------------------------------------- */
.pipeline { position: relative; display: grid; justify-items: center; gap: 6px; pointer-events: auto; }
.pipe-steps { display: flex; align-items: center; gap: 6px; margin: 0; padding: 0; list-style: none; flex-wrap: wrap; justify-content: center; }
.pipe-steps li { display: flex; align-items: center; gap: 6px; }
.pipe-arrow { color: var(--muted); font: 400 11px/1 var(--f-mono); }
.pipe-step {
  display: inline-flex; align-items: baseline; gap: 6px; padding: 4px 10px; border-radius: 12px;
  border: 1px solid var(--line-strong); background: rgba(7, 18, 28, 0.7);
  font: 500 10.5px/1.2 var(--f-mono); letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted);
}
.pipe-step small { font-size: 10px; letter-spacing: 0; text-transform: none; color: var(--text); }
.pipe-step.is-done { color: var(--glow); }
.pipe-step.is-run { color: var(--amber); border-color: var(--amber); box-shadow: 0 0 10px rgba(255, 181, 71, 0.45); }
.pipe-step.is-fail { color: var(--alert); border-color: rgba(255, 90, 78, 0.6); }
.pipe-step[aria-expanded="true"] { background: rgba(127, 219, 255, 0.14); }
.pipe-now { margin: 0; min-height: 1.4em; max-width: 60ch; font: 400 12px/1.4 var(--f-mono); color: var(--text);
  text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.step-details {
  position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%); z-index: 3;
  width: min(520px, 92vw); max-height: 300px; overflow: auto; padding: 12px 14px; border-radius: 6px;
  border: 1px solid var(--line-strong); background: rgba(4, 9, 15, 0.96); box-shadow: 0 14px 40px rgba(0, 0, 0, 0.5);
  font: 400 12px/1.5 var(--f-mono); color: var(--text); user-select: text;
}
.step-details h4 { margin: 0 0 4px; font: 600 12px/1.3 var(--f-mono); color: var(--glow); display: flex; gap: 8px; }
.step-details h4 small { color: var(--muted); font-weight: 400; }
.step-details h4 em { color: var(--alert); font-style: normal; }
.step-details section + section { margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--line); }
.step-details dl { margin: 0; display: grid; gap: 2px; }
.step-details dl div { display: grid; grid-template-columns: 8em minmax(0, 1fr); gap: 8px; }
.step-details dt { color: var(--muted); }
.step-details dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.step-details-close { position: absolute; top: 4px; right: 6px; border: 0; background: none; color: var(--muted); font-size: 16px; }
.step-details-empty { margin: 0; color: var(--muted); }
.gauges { display: inline-flex; gap: 12px; flex: none; }
.gauge i { font-style: normal; color: var(--muted); }
.gauge { color: var(--text); font-variant-numeric: tabular-nums; }
.jobs { display: inline-flex; gap: 8px; flex: none; }
.tele-chip--approval { color: var(--amber); border-color: rgba(255, 181, 71, 0.45); }
.entry-ms { grid-column: 2; justify-self: start; margin-top: 2px; font: 400 10px/1 var(--f-mono); color: var(--muted); }
```
Also change the stage's state label so the pipeline fits: in `.stage` keep `gap: 12px`; nothing else.

- [ ] **Step 4: Run the tests**

Run: `cd web && npm test`
Expected: all pass.

- [ ] **Step 5: Browser checks for the board**

In `web/e2e/interact.js`, before the final `const pre = …` line, add:
```js
  const ev = (o) => ({ trace: 500, detail: null, key: o.key || o.phase, t: 0, ms: null, ok: null, ...o });
  hud.live(ev({ phase: 'heard', state: 'end', label: 'Ще вали ли утре?', detail: { source: 'voice', google: 'ще вали ли утре', whisper: 'Ще вали ли утре?' }, ms: 140 }));
  hud.live(ev({ phase: 'understood', state: 'start', label: 'choosing' }));
  hud.live(ev({ phase: 'understood', state: 'end', label: 'quick command', detail: { command: 'will_it_rain' }, ms: 2, ok: true }));
  hud.live(ev({ phase: 'skill', state: 'start', label: 'will_it_rain', key: 'will_it_rain' }));
  await wait(100);
  check('pipeline shows the running skill', document.querySelector('.pipe-step[data-phase="skill"]')?.className.includes('is-run'));
  document.querySelector('.pipe-step[data-phase="heard"]').click();
  await wait(100);
  check('heard details show both transcripts', document.querySelector('.step-details')?.textContent.includes('ще вали ли утре'));
  hud.live(ev({ phase: 'skill', state: 'end', label: 'will_it_rain', key: 'will_it_rain', ms: 380, ok: true }));
  hud.live(ev({ phase: 'done', state: 'end', label: 'done', ok: true, ms: 900 }));
  hud.setGauges({ gpu: 21, vramUsed: 7000, vramTotal: 10240, cpu: 9, ram: 51 });
  await wait(100);
  check('gauges in the top bar', document.querySelector('.gauges')?.textContent.includes('GPU 21%'));
  check('the last answer time', document.querySelector('.gauges')?.textContent.includes('last 900 ms'));
  hud.live(ev({ trace: 999, phase: 'skill', state: 'end', label: 'ghost', key: 'ghost' }));
  check('events of unknown traces are ignored', !document.body.textContent.includes('ghost'));
```

Run: `npm run build && python web/e2e/run.py` (from `web/` then root)
Expected: `passed 36, failed 0`.

- [ ] **Step 6: Checkpoint** — all suites green.

---

### Task 10: Verification in the real window, performance, docs

**Files:**
- Modify: `README.md` (section „The network — how Orion thinks“ → „The eyes and the live board“), `docs/superpowers/plans/2026-10-02-baseline.md` (after-numbers)

- [ ] **Step 1: Full automated run** — `python -m pytest -q`; `cd web && npm test && npm run build`; `python web/e2e/run.py`; scratchpad `selftest_run2.py skills` (119/119); `synctest.py mp4 webm 4 21.37 15 0` (sound vs picture within one frame).

- [ ] **Step 2: Real window** — tell sir Orion restarts; relaunch; type „Хвърли монета“, „Колко е 17 по 23?“, „Какво ще е времето утре в Пловдив?“; screenshot (`shot.ps1`) after each; check: eyes visible and change (thinking squint, happy arcs after a skill), pipeline shows five steps with times, clicking „thinking“ shows streamed reasoning, gauges update; `logs/orion.log` has zero `[UI error]` lines. Minimise the window for 10 s and restore: gauges resume, eyes resume.

- [ ] **Step 3: Performance** — same procedure as Task 1 Step 6; record GPU idle %, video memory and the three answer times in the baseline file under „After“. Targets: GPU ≤ +10 points, memory ≤ +150 MB, answer time ≤ +5 %. If GPU is above target, lower `FPS` in `Eyes3D.jsx` to 24 and bloom `intensity` to 0.6, rebuild and re-measure.

- [ ] **Step 4: README** — replace the network section's first paragraph and the „core“ bullet with:
```markdown
## The eyes and the live board

In the centre are Orion's eyes (3D, `web/src/components/Eyes3D.jsx`; 2D fallback without WebGL). They show
its state: blue and looking around while waiting, amber while listening, squinting while thinking, a voice
wave while speaking, ^ ^ after a finished task, red and tilted after an error, green in test mode and
sleepy after 10 quiet minutes. They follow the mouse and glance at the skill that is running.

Under the eyes the live board shows every request step by step — heard → understood → thinking → skill →
speaking — with the time of each step; click a step to see what exactly happened (both transcripts, which
skills the model saw, its reasoning as it streams, the skill's arguments and result). The top bar shows
the GPU, video memory, processor and memory once a second, the speed of the last answer (tokens/s) and
its total time; test mode, reels and proposals waiting for approval appear next to them.
```

- [ ] **Step 5: Tell sir the result** (Bulgarian, short): what changed, the measured numbers versus the baseline, anything that did not meet a target; offer to upload to GitHub (do not push unasked).
