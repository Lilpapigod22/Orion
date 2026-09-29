"""Изчислява колко дни остават до дадена дата."""
from datetime import datetime

from orion import orion_tool


@orion_tool
def days_until_date(date_str: str) -> str:
    """Изчислява колко дни остават до дадена дата.

    Args:
        date_str: Дата в формат 'YYYY-MM-DD'.
    """
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        current_date = datetime.now()
        delta = target_date - current_date
        if delta.days < 0:
            return f"Дадената дата е минала. Минали са {abs(delta.days)} дни."
        return f"Остават {delta.days} дни до датата {date_str}."
    except ValueError as e:
        if "unconverted data remains" in str(e):
            raise ValueError("Невалиден формат на датата. Правилен формат е 'YYYY-MM-DD'.") from e
        raise
