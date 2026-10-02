"""
Understanding colloquial Bulgarian.

Sir talks the way people talk: „кво“, „шъ“, „нема“, „блутута“, „десктопа“, „двайсет и пет“.
Speech recognition writes English words in Cyrillic („уърдовски файл“, „пи ди еф“).
`normalize()` turns these forms into the words the reflexes and the language model understand
best. Only whole words are replaced, and only where the meaning is unambiguous.
"""
import re

# Colloquial and dialect forms -> standard ones.
COLLOQUIAL = {
    "кво": "какво", "к'во": "какво", "квото": "каквото", "шъ": "ще", "ша": "ще", "щъ": "ще",
    "нема": "няма", "немам": "нямам", "немаш": "нямаш", "немате": "нямате", "немаме": "нямаме",
    "айде": "хайде", "сичко": "всичко", "сички": "всички", "сичките": "всичките",
    "некой": "някой", "нещу": "нещо", "некъв": "някакъв", "некаква": "някаква", "некакво": "някакво",
    "некви": "някакви", "некога": "някога", "некъде": "някъде",
    "тоз": "този", "таз": "тази", "туй": "това", "онуй": "онова", "моа": "мога",
    "мойта": "моята", "твойта": "твоята", "мойто": "моето", "твойто": "твоето",
    "мерси": "благодаря", "окей": "добре", "ок": "добре", "окей.": "добре",
    "скил": "умение", "скила": "умението", "скилът": "умението", "скилове": "умения",
    "скиловете": "уменията", "скилс": "умения",
}

# English names as speech recognition writes them -> the real name.
_TERMS = [
    (r"(?:word|уърд|уорд|ворд)(?:овск(?:и|ия|ият|а|ата|о|ото)|а|ът)?", "Word"),
    (r"(?:excel|ексел|ексъл|иксел)(?:ск(?:и|ия|ият|а|ата|о|ото)|а|ът)?", "Excel"),
    (r"(?:power ?point|пауър ?пойнт)(?:а|ът)?", "PowerPoint"),
    (r"(?:pdf|пдф|пи ?ди ?еф)(?:-?а|-?ът|-?че|-?то)?", "PDF"),
    (r"(?:bluetooth|блутут|блу ?тут|блутуут|блутуд)(?:-?а|-?ът)?", "Bluetooth"),
    (r"(?:wi-?fi|уай ?фай|вай ?фай)(?:-?а|-?ят|-?то)?", "Wi-Fi"),
    (r"десктопа", "работния плот"),
    (r"десктопът|десктоп", "работният плот"),
]
_TERM_RES = [(re.compile(rf"(?<![\w-]){p}(?![\w-])", re.IGNORECASE), r) for p, r in _TERMS]

# Hesitation sounds: „ъъъ“, „ммм“, „ами“ at the start.
_HESITATION_RE = re.compile(r"(?<!\w)(?:ъ{2,}|м{3,}|е{3,}|а{3,})(?!\w)[,.]?\s*", re.IGNORECASE)
_LEADING_RE = re.compile(r"^\s*(?:ами|абе|ъ|ъм)[\s,]+", re.IGNORECASE)

# --- Numbers in words -> digits -----------------------------------------------------------------
UNITS = {"нула": 0, "един": 1, "една": 1, "едно": 1, "два": 2, "две": 2, "три": 3, "четири": 4,
         "пет": 5, "шест": 6, "седем": 7, "осем": 8, "девет": 9}
TEENS = {"десет": 10, "единадесет": 11, "единайсет": 11, "дванадесет": 12, "дванайсет": 12,
         "тринадесет": 13, "тринайсет": 13, "четиринадесет": 14, "четиринайсет": 14,
         "петнадесет": 15, "петнайсет": 15, "шестнадесет": 16, "шестнайсет": 16,
         "седемнадесет": 17, "седемнайсет": 17, "осемнадесет": 18, "осемнайсет": 18,
         "деветнадесет": 19, "деветнайсет": 19}
TENS = {"двадесет": 20, "двайсет": 20, "тридесет": 30, "трийсет": 30, "четиридесет": 40,
        "четирийсет": 40, "четирсет": 40, "петдесет": 50, "шейсет": 60, "шестдесет": 60,
        "седемдесет": 70, "осемдесет": 80, "деветдесет": 90}
HUNDREDS = {"сто": 100, "двеста": 200, "триста": 300, "четиристотин": 400, "петстотин": 500,
            "шестстотин": 600, "седемстотин": 700, "осемстотин": 800, "деветстотин": 900}
_SMALL = UNITS | TEENS | TENS | HUNDREDS
_SCALES = {"хиляда": 1000, "хиляди": 1000, "милион": 1_000_000, "милиона": 1_000_000}
# After these words a small number („една минута“, „пет процента“) is a quantity, not an article.
_UNIT_WORDS = re.compile(
    r"(?:секунд|минут|час|ден|дни|дена|седмиц|месец|годин|процент|%|градус|пъти|лев|лева|евро|долар|"
    r"км|километ|метр|метър|стотинк|страниц|слайд|ред|колон)", re.IGNORECASE)
_BEFORE_NUMBER = {"на", "с", "до", "със"}
_TOKEN = re.compile(r"\w+|[^\w\s]+|\s+")


def _is_number_word(word: str) -> bool:
    return word.lower() in _SMALL or word.lower() in _SCALES


def _value(words: list[str]) -> int:
    total = current = 0
    for word in (w.lower() for w in words):
        if word in _SCALES:
            total += (current or 1) * _SCALES[word]
            current = 0
        else:
            current += _SMALL[word]
    return total + current


def _continues(last: str, following: str) -> bool:
    """Whether `following` continues the number: „сто двайсет“, „двайсет и пет“, „две хиляди“ — yes;
    „пет шест“, „пет и шест“ — no (those are two numbers)."""
    last, following = last.lower(), following.lower()
    if following in _SCALES:
        return last not in _SCALES
    if following not in _SMALL:
        return False
    if last in _SCALES:
        return True
    if last in HUNDREDS:
        return following not in HUNDREDS
    return last in TENS and following in UNITS


def numbers_to_digits(text: str) -> str:
    """„намали звука с двайсет“ -> „намали звука с 20“, „две хиляди и двайсет и шест“ -> „2026“.
    A lone „един/една/две…“ stays a word („един приятел“), except before a unit."""
    tokens = _TOKEN.findall(text)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if not _is_number_word(tokens[i]):
            out.append(tokens[i])
            i += 1
            continue
        words, end = [tokens[i]], i + 1
        while True:
            # „сто двайсет“ — the words are next to each other
            if (end + 1 < len(tokens) and tokens[end].isspace()
                    and _continues(words[-1], tokens[end + 1])):
                words.append(tokens[end + 1])
                end += 2
            # „двайсет и пет“ — with „и“ between them
            elif (end + 3 < len(tokens) and tokens[end].isspace() and tokens[end + 1].lower() == "и"
                  and tokens[end + 2].isspace() and _continues(words[-1], tokens[end + 3])):
                words.append(tokens[end + 3])
                end += 4
            else:
                break
        after = "".join(tokens[end:end + 4])
        before = next((t.lower() for t in reversed(out) if not t.isspace()), "")
        single_small = len(words) == 1 and _value(words) < 10
        at_end = not "".join(tokens[end:]).strip(" .,!?")
        if single_small and not _UNIT_WORDS.match(after.strip()) and not (before in _BEFORE_NUMBER and at_end):
            out.append("".join(tokens[i:end]))
        else:
            out.append(str(_value(words)))
        i = end
    return "".join(out)


def normalize(text: str) -> str:
    """Sir's request in “standard” Bulgarian — for the reflexes and the language model."""
    if not text:
        return text
    text = _HESITATION_RE.sub("", text)
    text = _LEADING_RE.sub("", text)
    for pattern, replacement in _TERM_RES:
        text = pattern.sub(replacement, text)

    def colloquial(match: re.Match) -> str:
        word = match.group(0)
        standard = COLLOQUIAL.get(word.lower())
        if not standard:
            return word
        return standard.capitalize() if word[0].isupper() else standard

    text = re.sub(r"\w+(?:'\w+)?", colloquial, text)
    text = numbers_to_digits(text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()
