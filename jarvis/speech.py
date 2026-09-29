"""
Разпознаване на реч: Google + Whisper (локално, на видеокартата) едновременно.

Двете се допълват: Google пише по-добре българските думи, Whisper — английските имена
(„Steam“, „Hearts of Iron“), които Google чува като „снимка“. Whisper работи само ако на
видеокартата има място — иначе остава само Google и нищо не се забавя.
"""
import os
import re
import subprocess
import threading
from pathlib import Path

import config

_model = None
_loading = threading.Lock()
status = "изключен"  # показва се при старт: „Whisper на видеокартата“ / „само Google“ / причина

# Фрази, които Whisper „чува“ в тишина или шум (от субтитрите, на които е учен).
_HALLUCINATIONS = re.compile(r"субтитри|абонирайте|благодаря за вниманието|продължение следва|"
                             r"amara\.org|www\.|\.com\b", re.IGNORECASE)


def _free_vram_mb() -> int:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return int(out.split()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return 0


def load() -> None:
    """Зарежда Whisper (веднъж). Вика се във фонова нишка, след като езиковият модел е в паметта."""
    global _model, status
    if config.STT_ENGINE == "google":
        status = "само Google"
        return
    with _loading:
        if _model is not None:
            return
        free = _free_vram_mb()
        if free < config.WHISPER_MIN_FREE_VRAM_MB:
            status = f"само Google (видеокартата е пълна: {free} MB свободни)"
            return
        try:
            for sub in ("cublas", "cudnn", "cuda_nvrtc"):  # библиотеките на CUDA са на диск D:
                folder = Path(config.CUDA_LIBS) / sub / "bin"
                if folder.is_dir():
                    os.add_dll_directory(str(folder))
                    os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            from faster_whisper import WhisperModel
            _model = WhisperModel(config.WHISPER_MODEL, device="cuda", compute_type="int8_float16",
                                  download_root=str(config.WHISPER_DIR))
            status = "Google + Whisper"
        except Exception as e:  # noqa: BLE001 — без Whisper слушането продължава с Google
            status = f"само Google (Whisper: {type(e).__name__})"
            print(f"[Слушане] Whisper не се зареди: {e}")


def _vocabulary() -> str:
    """Подсказка за Whisper: имената, които сър казва — игри, програми, градове."""
    try:
        from . import games
        game_names = ", ".join(g.name for g in games.installed()[:12])
    except Exception:  # noqa: BLE001
        game_names = ""
    return (f"Орион, пусни {game_names or 'Steam'}. Отвори Chrome, Steam, Discord, Spotify и YouTube. "
            "Попитай Claude. Какво е времето във Варна, София, Пловдив и Бургас? Колко е часът в Ню Йорк? "
            "Анализирай биткойна и евро долар. Напомни ми утре. Напиши молба в Word, таблица в Excel, "
            "презентация в PowerPoint и PDF. Включи Bluetooth и Wi-Fi, яркостта на 50.")


def whisper(pcm16: bytes) -> str | None:
    """Текстът от Whisper за 16 kHz / 16-bit моно запис, или None."""
    if _model is None:
        return None
    import numpy as np
    audio = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
    segments, _ = _model.transcribe(audio, language="bg", beam_size=5, initial_prompt=_vocabulary(),
                                    condition_on_previous_text=False)
    parts = [s.text.strip() for s in segments if s.no_speech_prob < 0.6]
    text = " ".join(p for p in parts if p).strip()
    if not text or _HALLUCINATIONS.search(text):
        return None
    return text


def available() -> bool:
    """Зареден ли е Whisper (нужен е за прекъсването с глас)."""
    return _model is not None


def words(pcm16: bytes) -> list[tuple[str, float, float]]:
    """Думите в кратък запис — (дума, начало, край в секунди). Бързо (без подсказка и с beam 1):
    за прекъсването с глас, докато Орион говори. Без подсказка, защото Whisper „чува“ думите
    от подсказката в шума."""
    if _model is None:
        return []
    import numpy as np
    audio = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
    segments, _ = _model.transcribe(audio, language="bg", beam_size=1, word_timestamps=True,
                                    condition_on_previous_text=False)
    found = [(w.word.strip(), w.start, w.end)
             for s in segments if s.no_speech_prob < 0.6 for w in (s.words or []) if w.word.strip()]
    if _HALLUCINATIONS.search(" ".join(w for w, _, _ in found)):
        return []
    return found


_cpu_model = None


def _model_for_files():
    """Моделът за дълги записи: на видеокартата, ако е зареден; иначе — на процесора (по-бавно,
    но видеокартата често е заета от езиковия модел и отворените програми)."""
    global _cpu_model
    if _model is not None:
        return _model
    with _loading:
        if _cpu_model is None:
            from faster_whisper import WhisperModel
            _cpu_model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8",
                                      download_root=str(config.WHISPER_DIR))
        return _cpu_model


def release_cpu_model() -> None:
    """Освобождава паметта (~1 GB) след рийловете."""
    global _cpu_model
    _cpu_model = None


def transcribe(audio, language: str | None = None) -> tuple[str, list[tuple[str, float, float]]]:
    """Дълъг запис (float32, 16 kHz) -> (език, [(дума, начало, край)]). Езикът се разпознава сам —
    за субтитрите на рийловете (клиповете от YouTube може да са на всякакъв език)."""
    try:
        model = _model_for_files()
    except Exception as e:  # noqa: BLE001 — без субтитри рийлът пак става
        print(f"[Слушане] Whisper за файлове не се зареди: {e}")
        return "", []
    # Без vad_filter: той изрязва пеенето с музика като „не реч“ и песните остават без субтитри.
    segments, info = model.transcribe(audio, language=language, beam_size=5, word_timestamps=True,
                                      condition_on_previous_text=False)
    found = [(w.word.strip(), w.start, w.end)
             for s in segments if s.no_speech_prob < 0.6 for w in (s.words or []) if w.word.strip()]
    if _HALLUCINATIONS.search(" ".join(w for w, _, _ in found)):
        found = [w for w in found if not _HALLUCINATIONS.search(w[0])]
    return info.language, found


_WORD = re.compile(r"\w+", re.UNICODE)
# Английско име — и когато е залепено за българско окончание („Wordовски“, „Steam-а“).
_LATIN = re.compile(r"(?<![A-Za-zА-Яа-яЁё])[A-Za-z][A-Za-z']{2,}")


def choose(google: str | None, whisper_text: str | None) -> str | None:
    """По-добрият от двата резултата. Google — освен ако е орязал изречението или е изпуснал
    английско име, което Whisper е чул („отвори ми снимка“ срещу „отвори ми Steam“)."""
    if not google or not whisper_text:
        return google or whisper_text
    g_words, w_words = _WORD.findall(google), _WORD.findall(whisper_text)
    if len(g_words) < 0.7 * len(w_words):
        return whisper_text
    g_lower = google.lower()
    if any(word.lower() not in g_lower for word in _LATIN.findall(whisper_text)):
        return whisper_text
    return google
