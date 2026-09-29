"""
Прекъсване с глас: докато Орион говори, микрофонът слуша за „стоп“, „спри“, „Орион…“.

    „Стоп“, „спри“, „стига“, „млъкни“…   -> Орион млъква.
    „Орион, <команда>“                    -> млъква и изпълнява командата.
    „Орион“ или „чакай“                   -> млъква и Ви изслушва.

Микрофонът чува и самия Орион (от колоните), затова:
  - разпознава се локално, с Whisper на видеокартата — нищо не излиза в интернет;
  - дума-сигнал, която Орион сам казва в момента (или много прилича на такава), не се
    брои — това е ехото му.
Думите-сигнали са в config.py (BARGE_IN_STOP_WORDS, BARGE_IN_WAIT_WORDS, WAKE_WORDS).
"""
import audioop
import re
import threading
import time
from typing import Callable

import config

from . import speech
from .bulgarian import numbers_to_digits

_WORD = re.compile(r"\w+")
WAKE = {w.lower() for w in config.WAKE_WORDS}
STOP = {w.lower() for w in config.BARGE_IN_STOP_WORDS}
WAIT = {w.lower() for w in config.BARGE_IN_WAIT_WORDS}


def _words(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in _WORD.findall(text or "")]


def _echo(word: str, own: set[str]) -> bool:
    """Думата е от това, което Орион казва в момента (Whisper може да я чуе леко различно)."""
    if word in WAKE:
        return bool(own & WAKE)
    return word in own or (len(word) >= 4 and any(o[:4] == word[:4] for o in own if len(o) >= 4))


def fresh_words(heard: str, spoken: str) -> list[str]:
    """Думите, които не са ехо от гласа на Орион."""
    own = set(_words(numbers_to_digits(spoken)))  # Whisper пише числата с цифри: „двадесет“ -> „20“
    fresh = []
    for word in _words(heard):
        if word == "100" and "100" not in own:
            word = "стоп"  # Whisper често чува „стоп“ като „сто“ и го пише „100“
        if not _echo(word, own):
            fresh.append(word)
    return fresh


_POLITE = {"де", "бе", "моля", "те", "ти", "сега", "малко", "за", "момент", "ей", "хей"}


def _only_signals(words: list[str]) -> bool:
    return all(w in WAKE | STOP | WAIT | _POLITE for w in words)


def only_signals(text: str) -> bool:
    """„Орион, стоп“, „чакай малко“ — само думи-сигнали, без команда."""
    return _only_signals(_words(text))


def verdict(heard: str, spoken: str) -> str | None:
    """Какво иска сър, докато Орион говори: "stop", "command" (каза „Орион, …“), "listen"
    (само „Орион“ или „чакай“ — ще каже командата след малко) или None (ехо или шум)."""
    fresh = fresh_words(heard, spoken)
    has_wake = any(w in WAKE for w in fresh)
    if any(w in STOP for w in fresh) and (not has_wake or _only_signals(fresh)):
        return "stop"
    if has_wake and not _only_signals(fresh):
        return "command"
    if has_wake or any(w in WAIT for w in fresh):
        return "listen"
    return None


class Monitor:
    """Слуша, докато Орион говори. Вика `on_trigger(вид)` в мига, в който сър го прекъсне,
    и — ако след „Орион“ има команда — записва я в `command_audio` (speech_recognition.AudioData)."""

    # Сравнено на смесен запис (ехо + глас): 3 s хващат думата в повече прозорци от 2 s, а една
    # проверка отнема ~0.2 s на видеокартата. Без „hotwords“ — с тях Whisper „чува“ думите-сигнали в ехото.
    WINDOW = 3.0          # секунди звук, които Whisper гледа наведнъж
    STEP = 0.25           # колко често
    SILENCE = 1.0         # толкова тишина след командата = „свърших“
    WAIT_FOR_SPEECH = 6.0 # след „Орион“ или „чакай“ — колко чака да заговорите
    MAX_COMMAND = 15.0

    def __init__(self, microphone, energy_threshold: float, spoken: str, on_trigger: Callable[[str], None]):
        self.microphone = microphone
        self.threshold = max(float(energy_threshold), 50.0)
        self.spoken = spoken
        self.on_trigger = on_trigger
        self.kind: str | None = None
        self.heard = ""
        self.command_audio = None
        self._frames: list[bytes] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="barge-in")

    def start(self) -> None:
        self._thread.start()

    def finish(self, timeout: float | None = None) -> None:
        """Говорът свърши: спира слушането — или изчаква да се запише командата на сър."""
        if self.kind is None:
            self._stop.set()
        self._thread.join(self.MAX_COMMAND + 5 if timeout is None else timeout)
        self._stop.set()

    # --- Вътрешно --------------------------------------------------------------------------------
    def _run(self) -> None:
        try:
            with self.microphone as source:
                reader = threading.Thread(target=self._read, args=(source,), daemon=True, name="barge-in-mic")
                reader.start()
                try:
                    self._watch(source)
                finally:
                    self._stop.set()
                    reader.join(2)
        except Exception as e:  # noqa: BLE001 — без прекъсване, но Орион продължава да говори
            print(f"[Прекъсване] Микрофонът не се отвори: {e}")

    def _read(self, source) -> None:
        # Отделна нишка: докато Whisper мисли, звукът продължава да се записва без дупки.
        while not self._stop.is_set():
            data = source.stream.read(source.CHUNK)
            with self._lock:
                self._frames.append(data)

    def _watch(self, source) -> None:
        import speech_recognition as sr
        rate, width = source.SAMPLE_RATE, source.SAMPLE_WIDTH
        per_second = rate / source.CHUNK
        window = max(1, int(self.WINDOW * per_second))
        checked = 0
        while not self._stop.wait(self.STEP):
            with self._lock:
                total = len(self._frames)
                frames = self._frames[-window:]
            if total == checked or not frames:
                continue
            checked = total
            raw = b"".join(frames)
            if audioop.rms(raw, width) < self.threshold * 0.6:
                continue  # тишина — никой не говори
            pcm = sr.AudioData(raw, rate, width).get_raw_data(convert_rate=16000, convert_width=2)
            found = speech.words(pcm)
            heard = " ".join(w for w, _, _ in found)
            kind = verdict(heard, self.spoken)
            if not kind or self._stop.is_set():
                continue
            self.kind, self.heard = kind, heard
            print(f"[Прекъсване] {kind}: {heard}")
            self.on_trigger(kind)
            if kind == "stop":
                return
            # Записът на командата започва от „Орион“ (по-ранното в прозореца е гласът на Орион),
            # а след „чакай“ — от сега. При „Орион“ без команда се чака сър да я каже.
            first = total - len(frames)  # номерът на първия запис в прозореца
            wake_at = next((s for w, s, _ in found if set(_words(w)) & WAKE), None)
            begin = first + int(max(0.0, wake_at - 0.2) * per_second) if wake_at is not None else total
            self._record_command(source, sr, begin, total, waiting=(kind == "listen"))
            return

    def _record_command(self, source, sr, begin: int, seen: int, waiting: bool) -> None:
        """Записва, докато сър говори; спира след секунда тишина."""
        width = source.SAMPLE_WIDTH
        started = last_voice = time.monotonic()
        spoke = not waiting
        while time.monotonic() - started < self.MAX_COMMAND:
            time.sleep(0.1)
            with self._lock:
                new = self._frames[seen:]
                seen = len(self._frames)
            if any(audioop.rms(data, width) > self.threshold for data in new):
                spoke, last_voice = True, time.monotonic()
            if spoke and time.monotonic() - last_voice > self.SILENCE:
                break
            if not spoke and time.monotonic() - started > self.WAIT_FOR_SPEECH:
                break
        if spoke:
            with self._lock:
                raw = b"".join(self._frames[begin:])
            self.command_audio = sr.AudioData(raw, source.SAMPLE_RATE, width)
