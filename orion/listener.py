"""
Listening module (Speech-to-Text).

Uses `speech_recognition` with the free Google Web Speech API.
Recording (capture) and recognition (recognize) are separate steps so that
the microphone is released while the text is recognised online.
"""
import threading

import speech_recognition as sr

import config

from . import speech


def _candidate_devices() -> list[int | None]:
    """The default microphone, then all other input devices (e.g. the webcam's)."""
    devices: list[int | None] = [None]
    try:
        import pyaudio
        audio = pyaudio.PyAudio()
        try:
            for i in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(i)
                api = audio.get_host_api_info_by_index(info["hostApi"])["name"]
                # MME is the most compatible driver; “Sound Mapper” is the same as “default”.
                if info["maxInputChannels"] > 0 and api == "MME" and "Mapper" not in info["name"]:
                    devices.append(i)
        finally:
            audio.terminate()
    except Exception:  # noqa: BLE001 — without pyaudio only “default” remains
        pass
    return devices


class Listener:
    def __init__(self, language: str = "bg-BG", timeout: int = 8, phrase_time_limit: int = 15):
        self.language = language
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        # How much silence means “I'm done”. The default is 0.8 s — it cuts in at every pause for thought.
        self.recognizer.pause_threshold = config.LISTEN_PAUSE_SECONDS
        self.recognizer.non_speaking_duration = min(0.8, config.LISTEN_PAUSE_SECONDS)
        # Without this the request to Google can hang forever if the internet drops.
        self.recognizer.operation_timeout = 10

        # The first microphone that actually opens. Calibrated against background noise — once.
        errors = []
        for device in _candidate_devices():
            try:
                microphone = sr.Microphone(device_index=device)
                with microphone as source:
                    print("[Слушане] Калибриране на микрофона... моля, тишина.")
                    self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self.microphone = microphone
                self.device = device
                return
            except Exception as e:  # noqa: BLE001 — try the next one
                errors.append(f"{device}: {e}")
        raise OSError("нито един микрофон не се отваря (" + "; ".join(errors) + ")")

    def capture(self, timeout: float | None = None) -> sr.AudioData | None:
        """Records one phrase from the microphone. None if nobody speaks in time."""
        with self.microphone as source:
            print("[Слушане] Слушам...")
            try:
                return self.recognizer.listen(
                    source, timeout=timeout or self.timeout, phrase_time_limit=self.phrase_time_limit
                )
            except sr.WaitTimeoutError:
                return None

    def recognize(self, audio: sr.AudioData) -> str | None:
        """Turns the recording into text: Google and Whisper at the same time, then the better one (orion/speech.py).
        None if no speech was recognised."""
        pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
        heard: dict[str, str | None] = {}
        thread = threading.Thread(target=lambda: heard.update(whisper=self._whisper(pcm)), daemon=True)
        thread.start()
        google, google_error = None, False
        try:
            google = self.recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            pass  # There was sound, but no speech was recognised.
        except (sr.RequestError, OSError) as e:  # OSError includes TimeoutError
            google_error = True
            print(f"[Слушане] Google не отговаря: {e}")
        thread.join(timeout=10)
        whisper_text = heard.get("whisper")
        # Google heard no speech — trust it: Whisper sometimes “hears” words in noise (even “Орион” from its prompt).
        if not google and not google_error:
            return None
        text = speech.choose(google, whisper_text)
        if text:
            extra = f"   (Google: {google} | Whisper: {whisper_text})" if google != whisper_text else ""
            print(f"[Вие] {text}{extra}")
        return text

    @staticmethod
    def _whisper(pcm: bytes) -> str | None:
        try:
            return speech.whisper(pcm)
        except Exception as e:  # noqa: BLE001 — Google remains
            print(f"[Слушане] Whisper: {e}")
            return None

    def listen(self, timeout: float | None = None) -> str | None:
        """Records and recognises one phrase (used by the console mode)."""
        audio = self.capture(timeout)
        return self.recognize(audio) if audio else None
