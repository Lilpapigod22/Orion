"""
Езици: превод на текст (Google Translate), кой е езикът и значението на дума.
"""
import json
import re
import urllib.parse
import urllib.request

from jarvis import jarvis_tool, web

LANGUAGES = {
    "английски": "en", "български": "bg", "немски": "de", "френски": "fr", "испански": "es", "италиански": "it",
    "руски": "ru", "турски": "tr", "гръцки": "el", "румънски": "ro", "сръбски": "sr", "македонски": "mk",
    "португалски": "pt", "холандски": "nl", "полски": "pl", "чешки": "cs", "украински": "uk", "китайски": "zh-CN",
    "японски": "ja", "корейски": "ko", "арабски": "ar", "иврит": "iw", "шведски": "sv", "норвежки": "no",
    "датски": "da", "фински": "fi", "унгарски": "hu", "хърватски": "hr", "албански": "sq", "хинди": "hi",
}
_NAMES = {v: k for k, v in LANGUAGES.items()}


def _translate(text: str, target: str) -> tuple[str, str]:
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&dt=t&tl="
           f"{target}&q=" + urllib.parse.quote(text))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    return "".join(part[0] for part in data[0] if part[0]), data[2]


def _code(language: str) -> str:
    language = language.strip().lower().removesuffix(" език")
    if language in LANGUAGES:
        return LANGUAGES[language]
    if re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", language):
        return language
    for name, code in LANGUAGES.items():
        if name[:5] in language:
            return code
    raise ValueError(f"не познавам езика „{language}“")


@jarvis_tool
def translate_text(text: str, to_language: str = "английски") -> str:
    """Умението превежда текст на друг език, предлагайки по-точни резултати от превода по памет чрез
    Google Translate. Използва се при молби за превода на конкретни фрази или съобщения, например:
    „Преведи на английски „добър вечер“", „Преводай това предложение на испански" или „Какво
    означава тази дума на немски?".

    Args:
        text: Текстът за превод.
        to_language: На кой език: "английски", "немски", "български"…
    """
    translated, source = _translate(text, _code(to_language))
    return f"Превод от {_NAMES.get(source, source)} на {to_language}: {translated}"


@jarvis_tool
def detect_language(text: str) -> str:
    """На какъв език е даден текст.

    Args:
        text: Текстът.
    """
    translated, source = _translate(text, "bg")
    return f"Текстът е на {_NAMES.get(source, source)}" + (f". На български: {translated}" if source != "bg" else ".")


@jarvis_tool
def define_word(word: str) -> str:
    """Значението на дума — българска или чужда.

    Args:
        word: Думата.
    """
    if re.fullmatch(r"[A-Za-z\- ]+", word.strip()):
        try:
            request = urllib.request.Request(
                "https://en.wiktionary.org/api/rest_v1/page/definition/" + urllib.parse.quote(word.strip()),
                headers={"User-Agent": "Mitko/1.0"})
            with urllib.request.urlopen(request, timeout=12) as response:
                entries = json.load(response).get("en", [])
            meanings = [f"{e['partOfSpeech']}: " + re.sub(r"<[^>]+>", "", e["definitions"][0]["definition"])
                        for e in entries[:3] if e.get("definitions")]
            if meanings:
                return f"„{word}“ (английски) — " + "; ".join(meanings) + " (Преведи обяснението на български.)"
        except OSError:
            pass
    hits = web.search(f"{word} значение на думата", max_results=3)
    snippets = " | ".join(h["snippet"] for h in hits)
    return f"Какво пишат за „{word}“: {snippets}" if snippets else f"Не намерих значение на „{word}“."
