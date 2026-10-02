"""
Web search and page reading — so Orion can check information.

Search goes through `ddgs` (DuckDuckGo and other engines, no key or sign-up).
Pages are read as text only: no scripts, menus or ads.
"""
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
MAX_PAGE_CHARS = 3500  # as much as the model can “read” without forgetting the conversation


def search(query: str, news: bool = False, max_results: int = 5, region: str = "bg-bg") -> list[dict]:
    """[{title, url, snippet, date}] — the top results for the query (region “wt-wt” — worldwide)."""
    from ddgs import DDGS  # Slow import — only when actually searching.
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
    """(title, text) of a page. The text is cut to MAX_PAGE_CHARS characters."""
    if not re.match(r"https?://", url):
        url = "https://" + url
    parts = urlparse(url)
    if not parts.netloc:
        raise ValueError(f"„{url}“ не е адрес на страница")
    # Addresses with Cyrillic („bg.wikipedia.org/wiki/Канбера“) must be encoded for the network.
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
    # Short lines are buttons, menus and labels — only sentences are kept.
    text = "\n".join(line for line in lines if len(line) >= 40)
    return parser.title.strip(), text[:MAX_PAGE_CHARS]
