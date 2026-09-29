"""
Умение за „обучение с глас“: JARVIS записва нещата, които му кажете да запомни,
във файл в папка `knowledge/`. Базата знания го засича автоматично, така че
информацията е достъпна веднага — и остава и след рестарт (дългосрочна памет).
"""
from datetime import datetime

import config
from jarvis import jarvis_tool

NOTES_FILE = config.KNOWLEDGE_DIR / "запомнени_бележки.md"


@jarvis_tool
def remember(fact: str) -> str:
    """Запомня трайно факт или бележка, когато сър каже „запомни, че...“.

    Args:
        fact: Фактът, който да се запомни, формулиран като пълно изречение.
    """
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n\n[{datetime.now():%d.%m.%Y %H:%M}] {fact}")
    return "Записано в дългосрочната памет."
