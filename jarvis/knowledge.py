"""
Система за Знания (опростен RAG — Retrieval-Augmented Generation).

1. Чете всички .txt / .md / .pdf файлове от папката `knowledge/`.
2. Нарязва ги на парчета (chunks) от ~800 символа.
3. При всеки въпрос намира най-релевантните парчета (BM25 търсене по ключови думи)
   и ги подава на модела като контекст.

Файловете се презареждат автоматично, когато се добави/промени нещо в папката —
не е нужно да рестартирате JARVIS.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}

# Често срещани думи, които не носят смисъл при търсене.
_STOPWORDS = {
    "и", "в", "на", "за", "с", "от", "да", "се", "е", "не", "че", "по", "до", "как", "какво",
    "кой", "коя", "кое", "кои", "ли", "са", "съм", "си", "ще", "то", "ми", "ти", "му", "ни",
    "the", "a", "an", "is", "are", "of", "to", "in", "and", "or", "what", "who", "how",
}


# Членове и окончания, които се махат, преди думите да се сравнят (най-дългите първо).
_SUFFIXES = sorted(
    ("ът", "ят", "ия", "ии", "ите", "ата", "ята", "ето", "ото", "ове", "ов", "ища", "ище",
     "ият", "а", "я", "о", "е", "и", "ъ"),
    key=len, reverse=True,
)


def _stem(word: str) -> str:
    """Груб български стемър: маха едно окончание и оставя първите 5 букви.

    Така „екипа“ и „екипът“ -> „екип“, „проекта“ и „проект“ -> „проек“ —
    просто, но ефективно за търсене без тежки NLP библиотеки.
    """
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    return word[:5]


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"\w+", text.lower())
    return [_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1]


def _read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader  # Импорт тук: pypdf е нужен само ако имате PDF-и.
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    # Бележките може да са записани от Notepad в UTF-16 или в старата кирилска кодировка cp1251.
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


def _split_into_chunks(text: str, chunk_size: int) -> list[str]:
    """Нарязва по параграфи, като ги групира до `chunk_size` символа."""
    chunks, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) > chunk_size:
            chunks.append(current)
            current = ""
        # Много дълъг параграф се реже на части.
        while len(paragraph) > chunk_size:
            chunks.append(paragraph[:chunk_size])
            paragraph = paragraph[chunk_size:]
        current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


@dataclass
class Chunk:
    source: str
    text: str
    tokens: Counter = field(repr=False)


class KnowledgeBase:
    def __init__(self, folder: Path, chunk_size: int = 800, top_k: int = 4, full_context_chars: int = 0):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self.top_k = top_k
        self.full_context_chars = full_context_chars
        self.chunks: list[Chunk] = []
        self._signature = None
        self._doc_freq: Counter = Counter()
        self._avg_len = 1.0

    # --- Зареждане ---------------------------------------------------------------
    def _files(self) -> list[Path]:
        return sorted(p for p in self.folder.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS)

    @property
    def document_count(self) -> int:
        return len(self._files())

    def _current_signature(self) -> tuple:
        """Отпечатък на папката — ако се промени, знанията се презареждат."""
        return tuple((str(p), p.stat().st_mtime, p.stat().st_size) for p in self._files())

    def reload_if_changed(self) -> None:
        signature = self._current_signature()
        if signature != self._signature:
            self._signature = signature
            self._load()

    def _load(self) -> None:
        self.chunks = []
        for path in self._files():
            try:
                text = _read_file(path)
            except Exception as e:  # noqa: BLE001
                print(f"[Знания] Не мога да прочета {path.name}: {e}")
                continue
            for piece in _split_into_chunks(text, self.chunk_size):
                self.chunks.append(Chunk(path.name, piece, Counter(_tokenize(piece))))

        self._doc_freq = Counter(term for c in self.chunks for term in c.tokens)
        self._avg_len = sum(sum(c.tokens.values()) for c in self.chunks) / max(len(self.chunks), 1)
        print(f"[Знания] Заредени {len(self.chunks)} парчета от {len(self._files())} файла.")

    # --- Търсене (BM25) ------------------------------------------------------------
    def search(self, query: str) -> list[Chunk]:
        self.reload_if_changed()

        # Малко знания -> моделът получава всичко. Така няма риск търсенето да пропусне нещо.
        if sum(len(c.text) for c in self.chunks) <= self.full_context_chars:
            return list(self.chunks)

        query_terms = set(_tokenize(query))
        if not query_terms or not self.chunks:
            return []

        n, k1, b = len(self.chunks), 1.5, 0.75
        scored = []
        for chunk in self.chunks:
            length = sum(chunk.tokens.values())
            score = 0.0
            for term in query_terms:
                tf = chunk.tokens.get(term, 0)
                if not tf:
                    continue
                df = self._doc_freq[term]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / self._avg_len))
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [chunk for _, chunk in scored[: self.top_k]]

    def build_context(self, query: str) -> str:
        """Готов текстов блок за добавяне към системния промпт (или празен низ)."""
        results = self.search(query)
        if not results:
            return ""
        parts = [f"[Източник: {c.source}]\n{c.text}" for c in results]
        return "Релевантна информация от личните документи на сър:\n\n" + "\n\n---\n\n".join(parts)
