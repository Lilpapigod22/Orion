"""
Неврален глас чрез `edge-tts` — същите естествени гласове като „Прочети на глас“ в Microsoft Edge.

Връща MP3 байтове; приложението ги пуска в прозореца, където реакторът
пулсира в ритъма на гласа. Изисква интернет — без него се ползва pyttsx3.
"""
import asyncio
import re

import edge_tts


def clean_for_speech(text: str) -> str:
    """Маха markdown символи, които гласът би прочел буквално."""
    text = re.sub(r"[*_#`>|~]+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [текст](линк) -> текст
    return re.sub(r"\s+", " ", text).strip()


class NeuralVoice:
    def __init__(self, voice: str, rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    async def _synthesize(self, text: str) -> bytes:
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch)
        chunks = [c["data"] async for c in communicate.stream() if c["type"] == "audio"]
        return b"".join(chunks)

    def synthesize(self, text: str) -> bytes | None:
        """MP3 аудио или None, ако синтезът е невъзможен (напр. няма интернет)."""
        text = clean_for_speech(text)
        if not text:
            return None
        try:
            return asyncio.run(self._synthesize(text)) or None
        except Exception as e:  # noqa: BLE001 — всяка грешка -> резервен глас
            print(f"[Глас] Невралният глас е недостъпен: {e}")
            return None
