
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BLOG_URL = "https://www.callofduty.com/blog"
STATE_FILE = Path("cod_seen_articles.json")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_COD", "")
PATTERN = re.compile(r"^/blog/(20\d{2})/(\d{2})/")
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_articles():
    response = requests.get(
        BLOG_URL, headers=HEADERS, timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = {}

    for a in soup.find_all("a", href=True):
        url = urljoin(BLOG_URL, a["href"])
        parsed = urlparse(url)

        if parsed.netloc not in (
            "www.callofduty.com", "callofduty.com"
        ):
            continue

        match = PATTERN.match(parsed.path)
        if not match:
            continue

        title = html.unescape(
            a.get_text(" ", strip=True)
        ).strip()

        if not title:
            continue

        url = parsed._replace(
            query="", fragment=""
        ).geturl()

        # Preferisci il titolo più completo.
        if len(title) > len(articles.get(url, {}).get("title", "")):
            articles[url] = {
                "title": title,
                "url": url,
                "year": int(match.group(1)),
                "month": int(match.group(2)),
            }

    return sorted(
        articles.values(),
        key=lambda a: (a["year"], a["month"]),
        reverse=True
    )


def send_to_discord(article):
    if not WEBHOOK:
        raise RuntimeError(
            "Secret DISCORD_WEBHOOK_COD mancante"
        )

    payload = {
        "username": "ARTYKO COD NEWS",
        "embeds": [{
            "title": article["title"][:256],
            "url": article["url"],
            "description": (
                "🎯 Nuovo articolo dal blog ufficiale "
                "di Call of Duty!"
            ),
            "color": 0x00D9D0,
            "footer": {
                "text": "ARTYKO NEWS NETWORK • CALL OF DUTY"
            },
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat()
        }]
    }

    response = requests.post(
        WEBHOOK,
        json=payload,
        timeout=30
    )
    response.raise_for_status()


def main():
    articles = get_articles()
    print(f"Articoli trovati: {len(articles)}")

    if not articles:
        raise RuntimeError(
            "Nessun articolo trovato: storico invariato"
        )

    if STATE_FILE.exists():
        seen = set(json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        ))
        new_articles = [
            a for a in articles
            if a["url"] not in seen
        ]
    else:
        seen = set()
        # Primo avvio: massimo tre articoli.
        new_articles = articles[:3]
        print("Primo avvio: invio di 3 articoli")

    print(f"Da pubblicare: {len(new_articles)}")

    # Prima i più vecchi, poi i più recenti.
    for article in reversed(new_articles):
        print("Pubblico:", article["title"])
        send_to_discord(article)
        time.sleep(2)

    # Memorizza gli articoli esistenti.
    seen.update(a["url"] for a in articles)

    STATE_FILE.write_text(
        json.dumps(
            sorted(seen),
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )
    print("Storico aggiornato")


if __name__ == "__main__":
    main()
