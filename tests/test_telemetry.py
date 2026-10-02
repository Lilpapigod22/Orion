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
