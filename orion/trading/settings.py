"""
trading_settings.json — the network, the Hyperliquid API keys (encrypted with Windows DPAPI: only this
Windows user on this PC can read them), the limits and the voice hours. Never in GitHub (.gitignore).
The language model has no skill that changes the limits — sir edits them here.
"""
import base64
import ctypes
import json
import os
import re
import threading
from ctypes import wintypes

import config

from .risk import Limits

_lock = threading.RLock()  # the watch (account stop) and the window/skill threads all write the file
SETTINGS_FILE = config.BASE_DIR / "trading_settings.json"
DEFAULTS = {
    "network": "testnet",
    "enabled": False,      # REAL TRADE button — Orion trades the real account by itself while it is on
    "demo": False,         # DEMO TEST button — Orion trades the demo accounts by itself
    "accounts": {},
    "limits": {"risk_pct": 2.0, "max_leverage": 10, "daily_loss_pct": 6.0, "max_positions": 3,
               "max_drawdown_pct": 40.0},
    "voice_hours": [8, 23],
    "announce_strength": 4,
}
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")
KEY_RE = re.compile(r"(?:0x)?[0-9a-fA-F]{64}")


def load() -> dict:
    with _lock:
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
    merged = {**DEFAULTS, **saved}
    merged["limits"] = {**DEFAULTS["limits"], **saved.get("limits", {})}
    merged["accounts"] = dict(saved.get("accounts", {}))
    return merged


def save(settings: dict) -> None:
    """Atomic: a reader never sees a half-written file (it would read as the testnet with no key)."""
    with _lock:
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".tmp")
        tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_FILE)


def limits() -> Limits:
    return Limits(**load()["limits"])


def network() -> str:
    return "mainnet" if load()["network"] == "mainnet" else "testnet"


def set_network(net: str) -> None:
    with _lock:
        settings = load()
        settings["network"] = "mainnet" if net == "mainnet" else "testnet"
        save(settings)


def enabled() -> bool:
    return bool(load()["enabled"])


def set_enabled(on: bool) -> None:
    with _lock:
        settings = load()
        settings["enabled"] = bool(on)
        save(settings)


def demo_on() -> bool:
    return bool(load()["demo"])


def set_demo(on: bool) -> None:
    with _lock:
        settings = load()
        settings["demo"] = bool(on)
        save(settings)


def account(net: str) -> tuple[str, str] | None:
    """(account address, agent private key) for the network, or None if not connected."""
    entry = load()["accounts"].get(net)
    if not entry:
        return None
    return entry["address"], unprotect(entry["key"])


def save_account(net: str, address: str, key: str) -> str:
    address, key = address.strip(), key.strip()
    if len(key.split()) >= 12:
        raise ValueError("Това прилича на думите за възстановяване на портфейла. Никога не ги давайте — нито на "
                         "мен, нито на никого. Трябва ми само API ключът от страницата API на Hyperliquid.")
    if not ADDRESS_RE.fullmatch(address):
        raise ValueError("Адресът трябва да започва с 0x и да има 40 знака след това.")
    if not KEY_RE.fullmatch(key):
        raise ValueError("API ключът трябва да е 64 знака (цифри и букви от a до f), по желание с 0x отпред.")
    key = key if key.startswith("0x") else "0x" + key
    with _lock:
        settings = load()
        settings["accounts"][net] = {"address": address, "key": protect(key)}
        save(settings)
    return f"Запазих API ключа за {'истинската мрежа' if net == 'mainnet' else 'тестовата мрежа'}."


# --- Windows DPAPI ------------------------------------------------------------------------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(function, data: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    if not function(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):  # UI_FORBIDDEN
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def protect(text: str) -> str:
    return base64.b64encode(_dpapi(ctypes.windll.crypt32.CryptProtectData, text.encode())).decode()


def unprotect(token: str) -> str:
    return _dpapi(ctypes.windll.crypt32.CryptUnprotectData, base64.b64decode(token)).decode()
