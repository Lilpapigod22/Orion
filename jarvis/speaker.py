"""
Модул за Говорене (Text-to-Speech).

Използва `pyttsx3` — работи офлайн със системните гласове (SAPI5 на Windows).
"""
import pyttsx3


class Speaker:
    def __init__(self, voice_hint: str = "bg", rate: int = 175, muted: bool = False):
        self.rate = rate
        self.muted = muted
        self.voice_id = self._find_voice(voice_hint)

    @staticmethod
    def _find_voice(hint: str) -> str | None:
        """Намира системен глас, чието име, id или език съдържа `hint`."""
        engine = pyttsx3.init()
        hint = hint.lower()
        try:
            for voice in engine.getProperty("voices"):
                languages = " ".join(str(lang) for lang in (voice.languages or []))
                haystack = f"{voice.id} {voice.name} {languages}".lower()
                if hint in haystack:
                    print(f"[Говор] Избран глас: {voice.name}")
                    return voice.id
            print(f"[Говор] Няма глас за '{hint}', използвам гласа по подразбиране.")
            return None
        finally:
            engine.stop()

    def say(self, text: str) -> None:
        print(f"[JARVIS] {text}")
        if self.muted or not text:
            return
        # Нов engine за всяко изречение: заобикаля известен бъг в pyttsx3 на Windows,
        # при който runAndWait() „замръзва“ след първото извикване.
        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        if self.voice_id:
            engine.setProperty("voice", self.voice_id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
