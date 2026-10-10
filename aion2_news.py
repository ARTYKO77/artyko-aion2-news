
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

NEWS_URL = "https://aion2.app/news"
STATE_FILE = Path("seen_articles.json")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_articles():
    response = requests.get(
        NEWS_URL, headers=HEADERS, timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = []
    seen = set()

    for link in soup.select('a[href*="/news/"]'):
        url = urljoin(NEWS_URL, link.get("href", ""))
        parsed = urlparse(url)

        if parsed.netloc != "aion2.app":
            continue
        if not re.fullmatch(r"/news/\d+", parsed.path):
            continue
        if url in seen:
            continue

        seen.add(url)

        heading = link.find(re.compile(r"^h[1-6]$"))
        if heading:
            title = heading.get_text(" ", strip=True)
        else:
            title = link.get_text(" ", strip=True)

        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue

        image = link.find("img")
        image_url = None

        if image:
            src = image.get("src")
            if src:
                image_url = urljoin(NEWS_URL, src)

        articles.append({
            "title": title[:250],
            "url": url,
            "image": image_url
        })

    return articles


def send_to_discord(article):
    embed = {
        "title": article["title"],
        "url": article["url"],
        "description": (
            "📰 Nuova notizia di AION 2!\n\n"
            "Clicca sul titolo per leggere l'articolo."
        ),
        "color": 0x00D5C8,
        "footer": {"text": "ARTYKO • AION 2 NEWS"}
    }

    if article["image"]:
        embed["image"] = {"url": article["image"]}

    response = requests.post(
        WEBHOOK_URL,
        json={
            "username": "ARTYKO NEWS",
            "embeds": [embed]
        },
        timeout=20
    )
    response.raise_for_status()


def main():
    articles = get_articles()
    print(f"Articoli trovati: {len(articles)}")

    if not articles:
        raise RuntimeError("Nessun articolo trovato")

    current_urls = {a["url"] for a in articles}

    if not STATE_FILE.exists():
        STATE_FILE.write_text(
            json.dumps(sorted(current_urls), indent=2),
            encoding="utf-8"
        )
        print("Prima esecuzione: storico inizializzato.")
        print("Nessuna vecchia notizia pubblicata.")
        return

    seen_urls = set(json.loads(
        STATE_FILE.read_text(encoding="utf-8")
    ))

    new_articles = [
        a for a in articles if a["url"] not in seen_urls
    ]

    print(f"Nuovi articoli: {len(new_articles)}")

    if new_articles and not WEBHOOK_URL:
        raise RuntimeError("Webhook Discord mancante")

    for article in reversed(new_articles):
        send_to_discord(article)
        seen_urls.add(article["url"])
        print("Pubblicato:", article["title"])

        STATE_FILE.write_text(
            json.dumps(sorted(seen_urls), indent=2),
            encoding="utf-8"
        )

    if not new_articles:
        print("Nessuna nuova notizia da pubblicare.")


if __name__ == "__main__":
    main()
