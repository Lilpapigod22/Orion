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
