"""Управление на мишката."""
import subprocess
from orion import orion_tool


@orion_tool
def mouse_control(action: str, x: int, y: int) -> str:
    """Използвай това умение, когато сър иска да премести мишката или да кликне.

    Args:
        action: Действие за изпълнение (move, click_left, click_right).
        x: Хоризонтална координата на екрана.
        y: Вертикална координата на екрана.
    """
    try:
        if action == "move":
            cmd = f'powershell -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Cursor].Position = New-Object System.Drawing.Point({x}, {y})"'
        elif action == "click_left":
            cmd = f'powershell -Command "Add-Type -AssemblyName System.Windows.Forms; $cursor = [System.Windows.Forms.Cursor]; $cursor.Position = New-Object System.Drawing.Point({x}, {y}); [System.Windows.Forms.SendKeys]::SendWait(\'{chr(0)}{chr(0)}\')"'
        elif action == "click_right":
            cmd = f'powershell -Command "Add-Type -AssemblyName System.Windows.Forms; $cursor = [System.Windows.Forms.Cursor]; $cursor.Position = New-Object System.Drawing.Point({x}, {y}); [System.Windows.Forms.SendKeys]::SendWait(\'{chr(0)}{chr(0)}\')"'
        else:
            raise ValueError(f"Неподдържано действие: {action}.")

        subprocess.run(cmd, shell=True, check=True)
        return f"Успешно изпълних {action} на ({x}, {y})."

    except subprocess.CalledProcessError as e:
        raise ValueError(f"Грешка при управление на мишката: {e}.")
