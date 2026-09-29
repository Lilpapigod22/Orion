"""
Модул за Слушане (Speech-to-Text).

Използва `speech_recognition` с безплатното Google Web Speech API.
Записът (capture) и разпознаването (recognize) са отделни стъпки, за да може
микрофонът да се освободи, докато текстът се разпознава по интернет.
"""
import threading

import speech_recognition as sr

import config

from . import speech


def _candidate_devices() -> list[int | None]:
    """Микрофонът по подразбиране, после всички останали входни устройства (напр. на уеб камерата)."""
    devices: list[int | None] = [None]
    try:
        import pyaudio
        audio = pyaudio.PyAudio()
        try:
            for i in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(i)
                api = audio.get_host_api_info_by_index(info["hostApi"])["name"]
                # MME е най-съвместимият драйвер; „Sound Mapper“ е същото като „по подразбиране“.
                if info["maxInputChannels"] > 0 and api == "MME" and "Mapper" not in info["name"]:
                    devices.append(i)
        finally:
            audio.terminate()
    except Exception:  # noqa: BLE001 — без pyaudio остава само „по подразбиране“
        pass
    return devices


class Listener:
    def __init__(self, language: str = "bg-BG", timeout: int = 8, phrase_time_limit: int = 15):
        self.language = language
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        # Колко тишина означава „свърших“. По подразбиране е 0.8 с — прекъсва при всяка пауза за мисъл.
        self.recognizer.pause_threshold = config.LISTEN_PAUSE_SECONDS
        self.recognizer.non_speaking_duration = min(0.8, config.LISTEN_PAUSE_SECONDS)
        # Без това заявката към Google може да виси вечно при прекъснат интернет.
        self.recognizer.operation_timeout = 10

        # Първият микрофон, който наистина се отваря. Калибриране спрямо фоновия шум — веднъж.
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
            except Exception as e:  # noqa: BLE001 — пробваме следващия
                errors.append(f"{device}: {e}")
        raise OSError("нито един микрофон не се отваря (" + "; ".join(errors) + ")")

    def capture(self, timeout: float | None = None) -> sr.AudioData | None:
        """Записва една фраза от микрофона. None, ако никой не заговори навреме."""
        with self.microphone as source:
            print("[Слушане] Слушам...")
            try:
                return self.recognizer.listen(
                    source, timeout=timeout or self.timeout, phrase_time_limit=self.phrase_time_limit
                )
            except sr.WaitTimeoutError:
                return None

    def recognize(self, audio: sr.AudioData) -> str | None:
        """Превръща записа в текст: Google и Whisper едновременно, после по-добрият (orion/speech.py).
        None, ако не е разпозната реч."""
        pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
        heard: dict[str, str | None] = {}
        thread = threading.Thread(target=lambda: heard.update(whisper=self._whisper(pcm)), daemon=True)
        thread.start()
        google, google_error = None, False
        try:
            google = self.recognizer.recognize_google(audio, language=self.language)
        except sr.UnknownValueError:
            pass  # Звук имаше, но не беше разпозната реч.
        except (sr.RequestError, OSError) as e:  # OSError включва TimeoutError
            google_error = True
            print(f"[Слушане] Google не отговаря: {e}")
        thread.join(timeout=10)
        whisper_text = heard.get("whisper")
        # Google не чу реч — вярваме му: Whisper понякога „чува“ думи в шума (дори „Орион“ от подсказката).
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
        except Exception as e:  # noqa: BLE001 — остава Google
            print(f"[Слушане] Whisper: {e}")
            return None

    def listen(self, timeout: float | None = None) -> str | None:
        """Записва и разпознава една фраза (използва се от конзолния режим)."""
        audio = self.capture(timeout)
        return self.recognize(audio) if audio else None
