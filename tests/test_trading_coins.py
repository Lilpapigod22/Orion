import pytest

from orion import trading


@pytest.mark.parametrize("text, coin", [
    ("биткойна", "BTC"), ("Какво ще прави биткойнът?", "BTC"), ("BTC", "BTC"), ("bitcoin", "BTC"),
    ("биткоин", "BTC"), ("етериума", "ETH"), ("етер", "ETH"), ("етерът", "ETH"), ("ETH", "ETH"),
    ("Ethereum", "ETH"), ("соланата", "SOL"), ("солана", "SOL"), ("SOL", "SOL"),
])
def test_coin_from_text(text, coin):
    assert trading.coin_from_text(text) == coin


def test_other_coins_are_refused():
    with pytest.raises(ValueError, match="само биткойн"):
        trading.coin_from_text("доги")


def test_coins_in_lists_every_coin_named():
    assert trading.coins_in("сравни биткойн и солана") == ["BTC", "SOL"]


def test_salt_and_ether_words_are_not_coins():
    assert trading.coins_in("сол и пипер") == []
    assert trading.coins_in("етерична мазнина") == []


@pytest.mark.parametrize("text", [
    "0x" + "ab" * 32,
    "ключът ми е " + "1f" * 32,
    " ".join(["abandon"] * 11 + ["about"]),
    " ".join(["zoo"] * 24),
])
def test_secrets_are_recognised(text):
    assert trading.looks_secret(text)


@pytest.mark.parametrize("text", [
    "Отвори лонг на биткойн", "0xAbC123", "what is the price of bitcoin today my friend",
    "Какво ще прави етериумът днес?",
])
def test_normal_text_is_not_a_secret(text):
    assert not trading.looks_secret(text)
