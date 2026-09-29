"""
Умения за проверка на информация в интернет: търсене и четене на страници.
"""
from urllib.parse import urlparse

from jarvis import jarvis_tool, web


@jarvis_tool
def search_web(query: str, news: bool = False) -> str:
    """Търси в интернет актуална информация — новини, цени, курсове, резултати, факти, рецепти.
    Използвай, когато не знаеш отговора със сигурност или той зависи от днешния ден.

    Args:
        query: Какво да се търси, с ключови думи, напр. "курс евро лев днес".
        news: true — само новини от последните дни.
    """
    hits = web.search(query, news=news)
    if not hits:
        return "Няма резултати."
    lines = []
    for i, hit in enumerate(hits, 1):
        source = urlparse(hit["url"]).netloc.removeprefix("www.")
        date = f", {hit['date']}" if hit["date"] else ""
        lines.append(f"{i}. {hit['title']} ({source}{date}) — {hit['snippet']} [адрес: {hit['url']}]")
    return ("Резултати от търсенето (отговори на сър с думи, кратко; ако откъсите не стигат, "
            "прочети най-подходящия адрес с read_webpage):\n" + "\n".join(lines))


@jarvis_tool
def read_webpage(url: str) -> str:
    """Прочита текста на уеб страница, за да отговориш по нейното съдържание.

    Args:
        url: Адресът на страницата, напр. от резултатите на search_web.
    """
    title, text = web.read_page(url)
    if not text:
        return f"Страницата „{title or url}“ няма текст, който мога да прочета."
    return f"Страница „{title}“:\n{text}"
