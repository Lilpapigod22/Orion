"""
Speech recognition: Google + Whisper (locally, on the graphics card) at the same time.

They complement each other: Google writes Bulgarian words better, Whisper English names
(„Steam“, „Hearts of Iron“), which Google hears as „снимка“. Whisper only runs if there is
room on the graphics card — otherwise only Google is used and nothing slows down.
"""
import os
import re
import subprocess
import threading
from pathlib import Path

import config

_model = None
_loading = threading.Lock()
status = "off"  # shown at start-up in the window: “Google + Whisper” / “Google only” / the reason

# Phrases Whisper “hears” in silence or noise (from the subtitles it was trained on).
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
    """Loads Whisper (once). Called on a background thread after the language model is in memory."""
    global _model, status
    if config.STT_ENGINE == "google":
        status = "Google only"
        return
    with _loading:
        if _model is not None:
            return
        free = _free_vram_mb()
        if free < config.WHISPER_MIN_FREE_VRAM_MB:
            status = f"Google only (graphics card full: {free} MB free)"
            return
        try:
            for sub in ("cublas", "cudnn", "cuda_nvrtc"):  # the CUDA libraries are on drive D:
                folder = Path(config.CUDA_LIBS) / sub / "bin"
                if folder.is_dir():
                    os.add_dll_directory(str(folder))
                    os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            from faster_whisper import WhisperModel
            _model = WhisperModel(config.WHISPER_MODEL, device="cuda", compute_type="int8_float16",
                                  download_root=str(config.WHISPER_DIR))
            status = "Google + Whisper"
        except Exception as e:  # noqa: BLE001 — without Whisper, listening carries on with Google
            status = f"Google only (Whisper: {type(e).__name__})"
            print(f"[Слушане] Whisper не се зареди: {e}")


def _vocabulary() -> str:
    """A prompt for Whisper: the names sir says — games, programs, cities."""
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
    """Whisper's text for a 16 kHz / 16-bit mono recording, or None."""
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
    """Whether Whisper is loaded (needed for voice interruption)."""
    return _model is not None


def words(pcm16: bytes) -> list[tuple[str, float, float]]:
    """The words in a short recording — (word, start, end in seconds). Fast (no prompt, beam 1):
    for voice interruption while Orion speaks. No prompt, because Whisper “hears” the prompt's
    words in noise."""
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
    """The model for long recordings: on the graphics card if loaded; otherwise on the processor (slower,
    but the graphics card is often busy with the language model and open programs)."""
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
    """Frees the memory (~1 GB) after the reels."""
    global _cpu_model
    _cpu_model = None


def transcribe(audio, language: str | None = None) -> tuple[str, list[tuple[str, float, float]]]:
    """A long recording (float32, 16 kHz) -> (language, [(word, start, end)]). The language is detected automatically —
    for the reels' subtitles (YouTube videos can be in any language)."""
    try:
        model = _model_for_files()
    except Exception as e:  # noqa: BLE001 — the reel still works without subtitles
        print(f"[Слушане] Whisper за файлове не се зареди: {e}")
        return "", []
    # No vad_filter: it cuts singing with music as “not speech” and songs end up without subtitles.
    segments, info = model.transcribe(audio, language=language, beam_size=5, word_timestamps=True,
                                      condition_on_previous_text=False)
    found = [(w.word.strip(), w.start, w.end)
             for s in segments if s.no_speech_prob < 0.6 for w in (s.words or []) if w.word.strip()]
    if _HALLUCINATIONS.search(" ".join(w for w, _, _ in found)):
        found = [w for w in found if not _HALLUCINATIONS.search(w[0])]
    return info.language, found


_WORD = re.compile(r"\w+", re.UNICODE)
# An English name — also when glued to a Bulgarian ending („Wordовски“, „Steam-а“).
_LATIN = re.compile(r"(?<![A-Za-zА-Яа-яЁё])[A-Za-z][A-Za-z']{2,}")


def choose(google: str | None, whisper_text: str | None) -> str | None:
    """The better of the two results. Google — unless it cut the sentence short or missed
    an English name Whisper heard („отвори ми снимка“ vs „отвори ми Steam“)."""
    if not google or not whisper_text:
        return google or whisper_text
    g_words, w_words = _WORD.findall(google), _WORD.findall(whisper_text)
    if len(g_words) < 0.7 * len(w_words):
        return whisper_text
    g_lower = google.lower()
    if any(word.lower() not in g_lower for word in _LATIN.findall(whisper_text)):
        return whisper_text
    return google
