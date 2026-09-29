"""
Автоматична подготовка на локалния модел в Ollama.

При старт Орион сам:
1. стартира Ollama, ако не работи;
2. изтегля модела, ако липсва (с прогрес);
3. създава производен модел с по-голям контекст ("orion-<модел>");
4. зарежда го във видеопаметта, за да е бърз първият отговор.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterator

# progress(съобщение, процент или None)
ProgressCallback = Callable[[str, float | None], None]


class OllamaError(RuntimeError):
    pass


class OllamaManager:
    def __init__(self, base_url: str, model: str, context: int, keep_alive: str = "30m"):
        # Приложението ползва OpenAI-съвместимия адрес (.../v1); тук ни трябва основният.
        self.api = base_url.rstrip("/").removesuffix("/v1")
        self.base_model = model if ":" in model else f"{model}:latest"
        self.model = f"orion-{self.base_model}" if context else self.base_model
        self.context = context
        self.keep_alive = keep_alive

    # --- HTTP помощници --------------------------------------------------------------
    def _post(self, path: str, payload: dict, timeout: float = 30) -> dict:
        request = urllib.request.Request(
            self.api + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")

    def _post_stream(self, path: str, payload: dict) -> Iterator[dict]:
        request = urllib.request.Request(
            self.api + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            for line in response:
                if line.strip():
                    yield json.loads(line)

    def installed_models(self) -> set[str]:
        with urllib.request.urlopen(self.api + "/api/tags", timeout=3) as response:
            return {m["name"] for m in json.load(response).get("models", [])}

    def is_running(self) -> bool:
        try:
            self.installed_models()
            return True
        except (urllib.error.URLError, OSError):
            return False

    # --- Стъпки ------------------------------------------------------------------------
    def _start_server(self) -> None:
        exe = shutil.which("ollama") or str(Path(os.getenv("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe")
        if not Path(exe).exists() and not shutil.which("ollama"):
            raise OllamaError("Ollama не е инсталиран. Изтеглете го от ollama.com.")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.Popen([exe, "serve"], creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            if self.is_running():
                return
            time.sleep(0.5)
        raise OllamaError("Ollama не отговаря. Стартирайте приложението Ollama ръчно.")

    def _models_dir(self) -> Path:
        return Path(os.getenv("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")

    def _download_size(self) -> int | None:
        """Размерът на модела в байтове според регистъра на Ollama (или None)."""
        name, _, tag = self.base_model.partition(":")
        repo = name if "/" in name else f"library/{name}"
        request = urllib.request.Request(
            f"https://registry.ollama.ai/v2/{repo}/manifests/{tag or 'latest'}",
            headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return sum(layer.get("size", 0) for layer in json.load(response).get("layers", []))
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def _check_disk_space(self) -> None:
        """Отказва сваляне, което би напълнило диска (пълен системен диск чупи Windows)."""
        folder = self._models_dir()
        folder.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(folder).free
        needed = (self._download_size() or 10 * 1024**3) + 2 * 1024**3  # + 2 GB резерв
        if free < needed:
            raise OllamaError(
                f"Няма достатъчно място на диска за {self.base_model}: нужни са "
                f"{needed / 1024**3:.1f} GB, свободни са {free / 1024**3:.1f} GB в {folder}. "
                f"Освободете място или преместете моделите чрез променливата OLLAMA_MODELS."
            )

    def _pull(self, progress: ProgressCallback) -> None:
        self._check_disk_space()
        for event in self._post_stream("/api/pull", {"model": self.base_model, "stream": True}):
            if "error" in event:
                raise OllamaError(f"Изтеглянето се провали: {event['error']}")
            total, done = event.get("total"), event.get("completed")
            if total and done is not None:
                progress(f"Изтеглям {self.base_model}", done / total * 100)

    def ensure_ready(self, progress: ProgressCallback) -> str:
        """Подготвя модела и връща името, което да се ползва в заявките."""
        if not self.is_running():
            progress("Стартирам Ollama", None)
            self._start_server()

        if self.base_model not in self.installed_models():
            progress(f"Изтеглям {self.base_model}", 0)
            self._pull(progress)

        if self.model != self.base_model:
            # Бързо и безопасно при всеки старт: ползва същите файлове на модела.
            result = self._post("/api/create", {
                "model": self.model, "from": self.base_model,
                "parameters": {"num_ctx": self.context}, "stream": False,
            })
            if result.get("status") != "success":
                raise OllamaError(f"Не успях да създам {self.model}: {result}")

        progress("Зареждам във видеопаметта", None)
        self.touch()
        return self.model

    def touch(self, keep_alive: str | None = None, timeout: float = 300) -> None:
        """Зарежда модела (или удължава престоя му в паметта). keep_alive="0" го освобождава."""
        self._post("/api/generate", {"model": self.model, "keep_alive": keep_alive or self.keep_alive},
                   timeout=timeout)
