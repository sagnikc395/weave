from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


@dataclass
class ParseResult:
    url: str
    title: str
    text: str
    links: list[str]
    status: int


def parse_html(url: str, html: str, status: int) -> ParseResult:
    """CPU-bound. Runs in ProcessPoolExecutor — no GIL contention."""
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)[:8000]

    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, str(a["href"])).split("#")[0]
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            links.append(href)

    return ParseResult(
        url=url,
        title=title,
        text=text,
        links=list(dict.fromkeys(links)),
        status=status,
    )
