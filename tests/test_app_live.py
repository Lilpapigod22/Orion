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


def test_a_failing_model_still_closes_every_step():
    from types import SimpleNamespace

    from orion.brain import Brain
    from tests.test_brain_stream import Knowledge, Memory, Tools

    def boom(**kwargs):
        raise RuntimeError("model down")

    class CountingKnowledge(Knowledge):
        document_count = 0

    brain = Brain(Tools(), CountingKnowledge(), Memory(), base_url="http://x", api_key="x", model="m", persona="p")
    brain.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom)))
    events = []
    orion = make_app([])
    orion.brain, orion.ollama = brain, None
    live.sink = events.append
    try:
        orion._answer("Колко е 17 по 23?", "text")
    finally:
        live.sink = None
    done_at = next(i for i, e in enumerate(events) if e["phase"] == "done")
    assert events[done_at]["ok"] is False and done_at == len(events) - 1
    for key in {e["key"] for e in events if e["state"] == "start"}:
        ends = [i for i, e in enumerate(events) if e["key"] == key and e["state"] == "end"]
        assert ends and ends[-1] < done_at, key


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
