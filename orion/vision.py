"""
Зрение: Орион гледа екрана или снимка и отговаря на въпрос за нея.

Моделът qwen3.5 разбира и картинки. Снимката на екрана остава на този компютър —
изпраща се само на локалния модел в Ollama, не в интернет.
"""
import base64
import io
import time
from typing import Callable

# Задават се от приложението (app.py / main.py) при старт.
client = None
model: str | None = None
# Прозорецът на Орион се скрива за миг, за да не закрива това, което сър гледа.
hide_window: Callable[[], None] = lambda: None
show_window: Callable[[], None] = lambda: None
minimize_window: Callable[[], None] = lambda: None  # за писане в друга програма

SYSTEM = ("Ти си Орион, асистентът на сър. Гледаш картина и отговаряш на въпроса му на български, "
          "учтиво, на „Вие“, "
          "кратко и конкретно (2–5 изречения). Ако има важен текст — цитирай го точно. "
          "Не измисляй неща, които не се виждат.")


def configure(llm_client, llm_model: str) -> None:
    global client, model
    client, model = llm_client, llm_model


def grab_screen(max_side: int = 1400):
    """Снимка на основния екран (без прозореца на Орион), смалена за модела."""
    from PIL import ImageGrab
    hide_window()
    try:
        time.sleep(0.35)  # Windows довършва скриването
        image = ImageGrab.grab()
    finally:
        show_window()
    image.thumbnail((max_side, max_side))
    return image


def ask_image(image, question: str) -> str:
    """Отговорът на модела за картинка (PIL Image)."""
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
