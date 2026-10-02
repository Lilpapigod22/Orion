"""
Confirmation from sir before actions that cannot be undone — sending an email,
deleting an event. The app shows a dialog with buttons; the console asks „д/н“ (y/n).
"""
from typing import Callable

# (title, short summary, full text, button label) -> approved or not.
# Replaced by app.py / main.py. Default — reject: nothing happens without sir.
handler: Callable[[str, str, str, str], bool] = lambda title, summary, body, accept: False


def ask(title: str, summary: str, body: str = "", accept: str = "Потвърди") -> bool:
    return bool(handler(title, summary, body, accept))
