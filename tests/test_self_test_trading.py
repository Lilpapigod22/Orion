from types import SimpleNamespace

from orion import self_test
from orion.trading import exchange


def test_the_sandbox_blocks_the_exchange():
    assert not exchange.blocked
    with self_test.Sandbox():
        assert exchange.blocked
    assert not exchange.blocked


def test_test_mode_checks_skills_and_understanding_every_round_without_trading(monkeypatch):
    tester = self_test.SelfTester(SimpleNamespace())
    calls = []
    monkeypatch.setattr(tester, "_check_skills", lambda report, store: calls.append(("skills", report.number)))
    monkeypatch.setattr(tester, "_check_understanding",
                        lambda report, store, invent: calls.append(("asks", report.number)))
    monkeypatch.setattr(tester, "_fix", lambda report, store: None)
    monkeypatch.setattr(tester, "_hud", lambda *args: None)
    monkeypatch.setattr(tester, "_load_store", lambda: {"asks": [], "skills": [], "no_case": []})
    monkeypatch.setattr(tester, "_save_store", lambda store: None)
    monkeypatch.setattr(tester, "_untested", lambda store: [])
    for number in range(1, 5):
        tester._round(self_test.Report(number))
    assert [c for c in calls if c[0] == "asks"] == [("asks", n) for n in range(1, 5)]
    assert [c for c in calls if c[0] == "skills"] == [("skills", 1), ("skills", 4)]
    assert not hasattr(tester, "_practice") and not hasattr(self_test.Report(1), "trading")
