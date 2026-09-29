"""
Потвърждение от сър преди действия, които не могат да се върнат — изпращане на писмо,
изтриване на събитие. Приложението показва прозорче с бутони; конзолата пита „д/н“.
"""
from typing import Callable

# (заглавие, кратко описание, пълен текст, надпис на бутона) -> одобрено ли е.
# Сменя се от app.py / main.py. По подразбиране — отказ: нищо не става без сър.
handler: Callable[[str, str, str, str], bool] = lambda title, summary, body, accept: False


def ask(title: str, summary: str, body: str = "", accept: str = "Потвърди") -> bool:
    return bool(handler(title, summary, body, accept))
