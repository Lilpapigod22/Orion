"""Tests run from the project root: `python -m pytest -q`."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest


@pytest.fixture(autouse=True)
def autopilot_state(monkeypatch, tmp_path):
    """Every test gets its own memory/trading_auto.json — switching REAL TRADE on writes it."""
    from orion.trading import autopilot
    monkeypatch.setattr(autopilot, "AUTO_FILE", tmp_path / "trading_auto.json")
