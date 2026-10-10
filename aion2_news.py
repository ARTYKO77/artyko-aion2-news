
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

NEWS_URL = "https://aion2.app/news"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def main():
    if not WEBHOOK_URL:
        raise RuntimeError("Webhook Discord non configurato")

    response = requests.get(
        NEWS_URL,
        headers={"User-Agent": "ARTYKO-News/1.0"},
        timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    article = None

    for link in soup.select('a[href*="/news/"]'):
        url = urljoin(NEWS_URL, link.get("href", ""))
        parsed = urlparse(url)

        if parsed.netloc != "aion2.app":
            continue

        if not re.fullmatch(r"/news/\d+", parsed.path):
            continue

        title = link.get_text(" ", strip=True)

        if title:
            article = (title, url)
            break

    if article is None:
        raise RuntimeError("Nessuna notizia trovata")

    full_text, url = article

    # Prima prova: ricaviamo il titolo prima
    # della descrizione, se possibile.
    title = full_text.split(" The ")[0]
    title = title[:250]

    payload = {
        "username": "ARTYKO NEWS",
        "embeds": [
            {
                "title": title,
                "url": url,
                "description": (
                    "📰 Notizia AION 2\n\n"
                    "Clicca sul titolo per leggere l'articolo."
                ),
                "color": 0x00D5C8,
                "footer": {
                    "text": "ARTYKO • AION 2 NEWS"
                }
            }
        ]
    }

    result = requests.post(
        WEBHOOK_URL,
        json=payload,
        timeout=20
    )
    result.raise_for_status()

    print("Messaggio di prova inviato a Discord!")
    print("Articolo:", url)


if __name__ == "__main__":
    main()
