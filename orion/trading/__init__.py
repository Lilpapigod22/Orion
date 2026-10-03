"""
Crypto forecasts and trading on Hyperliquid — Bitcoin, Ethereum and Solana.

Design: docs/superpowers/specs/2026-10-03-crypto-trading-design.md and 2026-10-03-autonomous-trading-design.md.
Every number (signals, backtest, risk) is computed in code; the language model only explains it. A real order
a skill asks for needs sir's „Одобри“ (orion/trading/exchange.py); while REAL TRADE is on, the autopilot
(orion/trading/autopilot.py) trades the checked strategies by itself within the hard limits.
"""
import re
from typing import Callable

import config

COINS = ("BTC", "ETH", "SOL")
NAMES = {"BTC": "Биткойн", "ETH": "Етериум", "SOL": "Солана"}
MEMORY = config.BASE_DIR / "memory"
CACHE_DIR = MEMORY / "trading_cache"
ONLY_THREE = "засега търгувам само биткойн, етериум и солана"

_COIN_RES = {
    "BTC": re.compile(r"биткойн|биткоин|bitcoin|\bbtc\b", re.IGNORECASE),
    "ETH": re.compile(r"етериум|ефириум|\bетер(?:а|ът)?\b|ethereum|\beth\b", re.IGNORECASE),
    "SOL": re.compile(r"солан|solana|\bsol\b", re.IGNORECASE),
}
_HEX64 = re.compile(r"(?:0x)?[0-9a-fA-F]{64}")
_SEED_LENGTHS = {12, 15, 18, 21, 24}

# app.py replaces it: shows the key dialog in the window ("testnet" or "mainnet").
show_key_dialog: Callable[[str], None] = lambda network: None
# app.py replaces it: moves a button in the window ("demo" = DEMO TEST, "real" = REAL TRADE).
on_switch: Callable[[str, bool], None] = lambda name, on: None


def coins_in(text: str) -> list[str]:
    """The coins named in the text, in the order BTC, ETH, SOL."""
    return [coin for coin, pattern in _COIN_RES.items() if pattern.search(text or "")]


def coin_from_text(text: str) -> str:
    """'BTC' for „биткойна“, „BTC“, „Bitcoin“…; ValueError for any other coin."""
    found = coins_in(text)
    if not found:
        raise ValueError(ONLY_THREE)
    return found[0]


def looks_secret(text: str) -> bool:
    """A private key (64 hex characters) or a recovery phrase (12–24 lowercase Latin words) —
    such text is never processed, logged or sent to the model."""
    text = text or ""
    if _HEX64.search(text):
        return True
    tokens = text.split()
    return len(tokens) in _SEED_LENGTHS and all(re.fullmatch(r"[a-z]+", token) for token in tokens)
