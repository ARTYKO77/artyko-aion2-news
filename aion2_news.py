
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://aion2.app/news"

def check_news():
    print("ARTYKO NEWS - Controllo notizie AION 2")

    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = []
    seen = set()

    for link in soup.select('a[href*="/news/"]'):
        href = urljoin(URL, link.get("href", ""))
        title = link.get_text(" ", strip=True)

        if not title or href in seen:
            continue

        seen.add(href)
        articles.append((title, href))

    if not articles:
        print("Nessun articolo trovato.")
        print("Potrebbe essere necessario adattare l'estrazione.")
        return

    for title, link in articles[:10]:
        print(f"\nTitolo: {title}")
        print(f"Link: {link}")

if __name__ == "__main__":
    check_news()
