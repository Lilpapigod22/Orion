"""
Зрение: „Митко, какво има на екрана?“, „прочети ми грешката“, „какво пише тук?“.
Снимката се гледа от локалния модел — не излиза от компютъра.
"""
from pathlib import Path

from jarvis import jarvis_tool, vision


@jarvis_tool
def look_at_screen(question: str = "Какво има на екрана?") -> str:
    """Поглежда екрана на сър и отговаря за това, което се вижда — текст, грешки, програми, картинки.
    За „какво има на екрана“, „прочети ми това“, „какво пише тук“, „помогни ми с тази грешка“.

    Args:
        question: Какво точно иска да знае сър, напр. "Каква е тази грешка и как да я оправя?".
    """
    return vision.ask_image(vision.grab_screen(), question)


@jarvis_tool
def look_at_image(path: str, question: str = "Какво има на снимката?") -> str:
    """Разглежда снимка от компютъра (файл) и отговаря за нея.

    Args:
        path: Пълен път до снимката, напр. от find_files.
        question: Въпросът за снимката.
    """
    from PIL import Image
    file = Path(path.strip().strip('"'))
    if not file.is_file():
        raise FileNotFoundError(f"няма файл {file}")
    image = Image.open(file)
    image.thumbnail((1400, 1400))
    return f"На снимката {file.name}: " + vision.ask_image(image, question)
