from types import SimpleNamespace

from orion import self_test
from orion.trading import exchange, practice


def test_the_sandbox_blocks_the_exchange():
    assert not exchange.blocked
    with self_test.Sandbox():
        assert exchange.blocked
    assert not exchange.blocked


def test_practice_every_round_the_old_checks_every_third(monkeypatch):
    tester = self_test.SelfTester(SimpleNamespace())
    calls = []
    monkeypatch.setattr(tester, "_practice", lambda report: calls.append(("practice", report.number)))
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
    assert [c for c in calls if c[0] == "practice"] == [("practice", n) for n in range(1, 5)]
    assert [c for c in calls if c[0] == "asks"] == [("asks", 1), ("asks", 4)]


def test_the_report_tells_the_practice_result():
    report = self_test.Report(2)
    report.trading = practice.Round(10240.0, 10000.0, 1, [], {"pullback": {"n": 4, "wins": 3, "r": 2.0}},
                                    "пробвам нови числа за „пробив“ в тренировката", "")
    assert report.summary() == ("тренировъчната сметка е 10 240 $ (+2.4 %), 4 приключили сделки, 3 на печалба; "
                                "пробвам нови числа за „пробив“ в тренировката.")
    markdown = report.markdown()
    assert "## Търговия (тренировка)" in markdown and "- отскок в тренда: 3 от 4, средно +0.50R" in markdown
    failed = self_test.Report(3)
    failed.trading_error = "OSError: no route"
    assert "тренировката по търговия не мина" in failed.summary()
