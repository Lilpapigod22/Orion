"""
Neural voice via `edge-tts` — the same natural voices as “Read aloud” in Microsoft Edge.

Returns MP3 bytes; the app plays them in the window, where the reactor
pulses with the voice. Needs the internet — without it pyttsx3 is used.
"""
import asyncio
import re

import edge_tts


def clean_for_speech(text: str) -> str:
    """Removes markdown symbols the voice would read out literally."""
    text = re.sub(r"[*_#`>|~]+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [text](link) -> text
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
        """MP3 audio, or None if synthesis is impossible (e.g. no internet)."""
        text = clean_for_speech(text)
        if not text:
            return None
        try:
            return asyncio.run(self._synthesize(text)) or None
        except Exception as e:  # noqa: BLE001 — any error -> fallback voice
            print(f"[Глас] Невралният глас е недостъпен: {e}")
            return None
