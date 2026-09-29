"""
Търсене в интернет и четене на страници — за да може Орион да проверява информация.

Търсенето минава през `ddgs` (DuckDuckGo и други търсачки, без ключ и регистрация).
Страниците се четат само като текст: без скриптове, менюта и реклами.
"""
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
MAX_PAGE_CHARS = 3500  # колкото моделът може да „прочете“, без да забрави разговора


def search(query: str, news: bool = False, max_results: int = 5, region: str = "bg-bg") -> list[dict]:
    """[{title, url, snippet, date}] — първите резултати за заявката (region „wt-wt“ — от целия свят)."""
    from ddgs import DDGS  # Бавен импорт — само когато наистина се търси.
    with DDGS() as ddgs:
        if news:
            hits = ddgs.news(query, region=region, max_results=max_results)
        else:
            hits = ddgs.text(query, region=region, max_results=max_results)
    return [{"title": h.get("title", ""), "url": h.get("href") or h.get("url", ""),
             "snippet": h.get("body", ""), "date": (h.get("date") or "")[:10]} for h in hits]


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg",
            "button", "select", "iframe", "template"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "tr", "br", "section", "article", "td", "dd"}

    def __init__(self):
        super().__init__()
        self.skip_depth = 0
        self.title = ""
        self._in_title = False
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip_depth:
            self.parts.append(data)


def read_page(url: str) -> tuple[str, str]:
    """(заглавие, текст) на страница. Текстът е съкратен до MAX_PAGE_CHARS знака."""
    if not re.match(r"https?://", url):
        url = "https://" + url
    parts = urlparse(url)
    if not parts.netloc:
        raise ValueError(f"„{url}“ не е адрес на страница")
    # Адреси с кирилица („bg.wikipedia.org/wiki/Канбера“) трябва да се кодират за мрежата.
    url = parts._replace(netloc=parts.netloc.encode("idna").decode("ascii"),
                         path=quote(parts.path, safe="/%:@!$&'()*+,;=~"),
                         query=quote(parts.query, safe="=&%+/:,;~")).geturl()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "bg,en;q=0.8"})
    with urllib.request.urlopen(request, timeout=15) as response:
        if "html" not in response.headers.get("Content-Type", "html"):
            raise ValueError("страницата не е текст (може би е файл или картинка)")
        raw = response.read(2_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
    parser = _TextExtractor()
    parser.feed(raw.decode(charset, errors="replace"))
    lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).split("\n")]
    # Кратките редове са бутони, менюта и надписи — остават само изреченията.
    text = "\n".join(line for line in lines if len(line) >= 40)
    return parser.title.strip(), text[:MAX_PAGE_CHARS]
