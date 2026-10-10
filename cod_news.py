
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

URL = "https://www.callofduty.com/blog"

def check_news():
    print("ARTYKO COD NEWS - Test lettura notizie")

    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = urljoin(URL, link["href"])
        path = urlparse(href).path

        if "/blog/20" not in path:
            continue

        if href in seen:
            continue

        seen.add(href)
        title = link.get_text(" ", strip=True)

        if title:
            articles.append((title, href))

    print(f"Articoli trovati: {len(articles)}")

    for title, link in articles[:5]:
        print("Titolo:", title[:200])
        print("Link:", link)
        print("---")

if __name__ == "__main__":
    check_news()
