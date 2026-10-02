"""
Vision: Orion looks at the screen or an image and answers a question about it.

The qwen3.5 model understands images too. The screenshot stays on this computer —
it is only sent to the local model in Ollama, not to the internet.
"""
import base64
import io
import time
from typing import Callable

# Set by the app (app.py / main.py) at start-up.
client = None
model: str | None = None
# Orion's window hides for a moment so it does not cover what sir is looking at.
hide_window: Callable[[], None] = lambda: None
show_window: Callable[[], None] = lambda: None
minimize_window: Callable[[], None] = lambda: None  # for typing into another program

SYSTEM = ("Ти си Орион, асистентът на сър. Гледаш картина и отговаряш на въпроса му на български, "
          "учтиво, на „Вие“, "
          "кратко и конкретно (2–5 изречения). Ако има важен текст — цитирай го точно. "
          "Не измисляй неща, които не се виждат.")


def configure(llm_client, llm_model: str) -> None:
    global client, model
    client, model = llm_client, llm_model


def grab_screen(max_side: int = 1400):
    """A screenshot of the main screen (without Orion's window), scaled down for the model."""
    from PIL import ImageGrab
    hide_window()
    try:
        time.sleep(0.35)  # Windows finishes hiding it
        image = ImageGrab.grab()
    finally:
        show_window()
    image.thumbnail((max_side, max_side))
    return image


def ask_image(image, question: str) -> str:
    """The model's answer about an image (PIL Image)."""
    if client is None:
        raise RuntimeError("езиковият модел още не е готов")
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    reply = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
            ]},
        ],
        reasoning_effort="none",
    )
    return (reply.choices[0].message.content or "").strip() or "Не успях да разбера какво има на картината."
