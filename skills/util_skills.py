"""
Инструменти: пароли, случайни числа, зар и монета, QR кодове, текст, кодиране, бройни системи,
римски числа, времеви печати, статистика, проценти и разделяне на сметка.
"""
import base64
import hashlib
import os
import random
import re
import secrets
import string
from datetime import datetime
from pathlib import Path
from statistics import mean, median, pstdev

from jarvis import folders, jarvis_tool


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in re.findall(r"-?\d+(?:[.,]\d+)?", text)]


@jarvis_tool
def generate_password(length: int = 16, symbols: bool = True) -> str:
    """Създава силна случайна парола и я копира в клипборда (не я казва на глас).

    Args:
        length: Дължина, от 8 до 64 (по подразбиране 16).
        symbols: true — и символи като !@#, false — само букви и цифри.
    """
    length = max(8, min(64, length))
    alphabet = string.ascii_letters + string.digits + ("!@#$%^&*-_=+?" if symbols else "")
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in password) and any(c.isupper() for c in password) and any(c.isdigit() for c in password):
            break
    import pyperclip
    pyperclip.copy(password)
    return f"Създадох парола от {length} знака и я копирах — поставете я с Ctrl+V. (Не я казвай на глас.)"


@jarvis_tool
def random_number(minimum: int = 1, maximum: int = 100) -> str:
    """Случайно число в интервал. За „кажи случайно число от 1 до 10“.

    Args:
        minimum: Най-малкото.
        maximum: Най-голямото.
    """
    low, high = sorted((minimum, maximum))
    return f"Случайното число е {random.SystemRandom().randint(low, high)}."


@jarvis_tool
def flip_coin() -> str:
    """Хвърля монета — ези или тура."""
    return f"Падна се {'ези' if secrets.randbelow(2) else 'тура'}."


@jarvis_tool
def roll_dice(count: int = 1, sides: int = 6) -> str:
    """Хвърля зар (или няколко). За „хвърли зар“, „хвърли два зара“.

    Args:
        count: Колко зара (1–10).
        sides: Колко страни има всеки зар (по подразбиране 6).
    """
    rolls = [secrets.randbelow(max(2, sides)) + 1 for _ in range(max(1, min(10, count)))]
    return f"Хвърлих: {', '.join(map(str, rolls))}" + (f" — общо {sum(rolls)}." if len(rolls) > 1 else ".")


@jarvis_tool
def pick_random(options: str) -> str:
    """Избира случайно от няколко възможности. За „избери между пица, суши и бургер“.

    Args:
        options: Възможностите, разделени със запетая или „или“.
    """
    choices = [o.strip() for o in re.split(r",|\bили\b|\bи\b", options) if o.strip()]
    if len(choices) < 2:
        return "Дайте ми поне две възможности."
    return f"Избирам: {secrets.choice(choices)}."


@jarvis_tool
def make_qr_code(text: str) -> str:
    """Прави QR код (за линк, Wi-Fi, текст) и го отваря, за да го сканирате с телефона.

    Args:
        text: Какво да съдържа кодът — адрес, текст или телефон.
    """
    import qrcode
    folder = folders.known().get("снимки", Path.home() / "Pictures") / "Орион"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"qr-{datetime.now():%Y%m%d-%H%M%S}.png"
    qrcode.make(text).save(path)
    os.startfile(path)
    return f"Направих QR кода и го отворих (запазен в {path.parent.name})."


@jarvis_tool
def count_text(text: str) -> str:
    """Брои думите, знаците и изреченията в текст.

    Args:
        text: Текстът.
    """
    words = re.findall(r"\w+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    return f"{len(words)} думи, {len(text)} знака ({len(text.replace(' ', ''))} без интервалите), {len(sentences)} изречения."


@jarvis_tool
def encode_base64(text: str) -> str:
    """Кодира текст в Base64.

    Args:
        text: Текстът за кодиране.
    """
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@jarvis_tool
def decode_base64(data: str) -> str:
    """Декодира Base64 обратно в текст.

    Args:
        data: Base64 низът.
    """
    return base64.b64decode(data.strip() + "=" * (-len(data.strip()) % 4)).decode("utf-8", errors="replace")


@jarvis_tool
def hash_text(text: str, algorithm: str = "sha256") -> str:
    """Хеш (отпечатък) на текст: sha256, sha1 или md5.

    Args:
        text: Текстът.
        algorithm: sha256 (по подразбиране), sha1 или md5.
    """
    name = algorithm.lower().replace("-", "")
    if name not in ("sha256", "sha1", "md5", "sha512"):
        raise ValueError("алгоритъмът трябва да е sha256, sha1, sha512 или md5")
    return f"{name}: {hashlib.new(name, text.encode('utf-8')).hexdigest()}"


@jarvis_tool
def convert_number_base(number: str, to_base: int = 2) -> str:
    """Превръща число между бройни системи: десетична, двоична (2), осмична (8), шестнадесетична (16).

    Args:
        number: Числото, напр. "255", "0xFF" или "0b1010".
        to_base: В коя система: 2, 8, 10 или 16.
    """
    value = int(number.strip().lower(), 0)
    shown = {2: bin(value), 8: oct(value), 10: str(value), 16: hex(value).upper().replace("0X", "0x")}.get(to_base)
    if shown is None:
        raise ValueError("системата трябва да е 2, 8, 10 или 16")
    return f"{number} = {shown}"


_ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
          (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


@jarvis_tool
def roman_numeral(value: str) -> str:
    """Превръща между арабски и римски числа: 2026 -> MMXXVI, XIV -> 14.

    Args:
        value: Число („2026“) или римско число („XIV“).
    """
    text = value.strip().upper()
    if text.isdigit():
        n, out = int(text), ""
        if not 0 < n < 4000:
            raise ValueError("римските числа са от 1 до 3999")
        for number, letters in _ROMAN:
            while n >= number:
                out, n = out + letters, n - number
        return f"{text} = {out}"
    total, i = 0, 0
    for number, letters in _ROMAN:
        while text.startswith(letters, i):
            total, i = total + number, i + len(letters)
    if i != len(text):
        raise ValueError(f"„{value}“ не е римско число")
    return f"{text} = {total}"


@jarvis_tool
def convert_timestamp(value: str) -> str:
    """Unix време (секунди от 1970) към дата и обратно: 1790000000 -> дата, „25.09.2026 12:00“ -> число.

    Args:
        value: Число или дата във вид „дд.мм.гггг чч:мм“.
    """
    text = value.strip()
    if re.fullmatch(r"\d{9,13}", text):
        seconds = int(text) / (1000 if len(text) == 13 else 1)
        return f"{text} = {datetime.fromtimestamp(seconds):%d.%m.%Y %H:%M:%S} (местно време)"
    moment = datetime.strptime(text, "%d.%m.%Y %H:%M" if ":" in text else "%d.%m.%Y")
    return f"{text} = {int(moment.timestamp())}"


@jarvis_tool
def number_stats(numbers: str) -> str:
    """Статистика за поредица от числа: сума, средно, медиана, минимум, максимум, отклонение.

    Args:
        numbers: Числата, разделени със запетаи или интервали, напр. "12, 15, 9, 22".
    """
    values = _numbers(numbers)
    if not values:
        raise ValueError("не виждам числа")
    return (f"{len(values)} числа: сума {sum(values):g}, средно {mean(values):.4g}, медиана {median(values):g}, "
            f"най-малко {min(values):g}, най-голямо {max(values):g}, стандартно отклонение {pstdev(values):.4g}.")


@jarvis_tool
def percent_change(old_value: float, new_value: float) -> str:
    """С колко процента се е променило нещо: от стара към нова стойност (цени, заплати, тегло…).

    Args:
        old_value: Старата стойност.
        new_value: Новата стойност.
    """
    if old_value == 0:
        raise ValueError("старата стойност не може да е нула")
    change = (new_value / old_value - 1) * 100
    return f"От {old_value:g} на {new_value:g}: {'+' if change >= 0 else ''}{change:.2f}% ({new_value - old_value:+g})."


@jarvis_tool
def split_bill(total: float, people: int, tip_percent: float = 0) -> str:
    """Разделя сметка между хора, с бакшиш по желание. За „разделѝ 120 лева на 4 с 10% бакшиш“.

    Args:
        total: Сумата на сметката.
        people: Между колко души.
        tip_percent: Бакшиш в проценти (0 — без).
    """
    people = max(1, people)
    with_tip = total * (1 + tip_percent / 100)
    tip = f" (с {tip_percent:g}% бакшиш общо {with_tip:.2f})" if tip_percent else ""
    return f"По {with_tip / people:.2f} на човек{tip}."
