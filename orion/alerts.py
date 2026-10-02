"""
Price alerts („кажи ми, когато биткойнът стигне 90 000“ — tell me when bitcoin hits 90,000) and an asset portfolio.
Stored in memory/. The app checks the alerts every few minutes.
"""
import json
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ALERTS = BASE_DIR / "memory" / "price_alerts.json"
PORTFOLIO = BASE_DIR / "memory" / "portfolio.json"
_lock = threading.Lock()


def load(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def triggered() -> list[str]:
    """Checks the alerts and returns the messages for those triggered (they are removed)."""
    from . import markets
    with _lock:
        items = load(ALERTS)
    if not items:
        return []
    messages, keep = [], []
    for item in items:
        try:
            name, price, _, currency = markets.quote(item["symbol"])
        except Exception:  # noqa: BLE001 — no connection: try again next time
            keep.append(item)
            continue
        hit = price >= item["price"] if item["direction"] == "above" else price <= item["price"]
        if hit:
            word = "надмина" if item["direction"] == "above" else "падна под"
            messages.append(f"Сър, {name} {word} {markets._fmt(item['price'])} — сега е {markets._fmt(price)} {currency}.")
        else:
            keep.append(item)
    if len(keep) != len(items):
        with _lock:
            save(ALERTS, keep)
    return messages
