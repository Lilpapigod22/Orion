import threading

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
    assert events[-1]["ok"] is False  # a failed skill makes the whole request „failed"


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


def test_the_sink_runs_without_holding_the_lock():
    held = []

    def sink(event):
        def probe():
            got = live._lock.acquire(timeout=0.5)
            if got:
                live._lock.release()
            held.append(got)
        worker = threading.Thread(target=probe)
        worker.start()
        worker.join()

    live.sink = sink
    try:
        live.begin("x")
        live.end()
    finally:
        live.sink = None
    assert held == [True, True]


def test_a_new_request_closes_a_forgotten_one(events):
    first = live.begin("a")
    live.start("thinking", "round 1")
    second = live.begin("b")
    done = [e for e in events if e["phase"] == "done"]
    assert len(done) == 1 and done[0]["trace"] == first and done[0]["ok"] is False
    assert events[-1]["trace"] == second and events[-1]["phase"] == "heard"
