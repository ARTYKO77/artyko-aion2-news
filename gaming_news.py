
import os
import re
import json
import html
import time
import hashlib
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

import requests

# ARTYKO GAMING NEWS
BASE_DIR = Path(__file__).resolve().parent
STATE = BASE_DIR / "gaming_seen_articles.json"
COVER = BASE_DIR / "gaming_cover.png"

WEBHOOK = os.getenv("DISCORD_WEBHOOK_GAMING", "")
DRY_RUN = os.getenv("GAMING_DRY_RUN", "true").lower() != "false"

FEEDS = {
    "IGN Italia": "https://it.ign.com/feed.xml",
    "GameSpot": "https://www.gamespot.com/feeds/game-news/"
}

MAX_PER_FEED = 30
FIRST_RUN_LIMIT = 3
MAX_PER_RUN = 3

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-Gaming-News/1.0"
})

# Escludiamo articoli poco adatti a un canale di notizie.
EXCLUDED = (
    "recensione", "review", "guida", "guide",
    "soluzione", "walkthrough", "trucchi",
    "offerta", "sconto", "coupon",
    "preorder", "pre-order", "compra ora",
    "migliori offerte", "best deals"
)


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return " ".join(value.split())


def normalize_title(title):
    title = unicodedata.normalize("NFKD", title)
    title = "".join(
        char for char in title
        if not unicodedata.combining(char)
    )
    return re.sub(
        r"[^a-z0-9]+", " ", title.lower()
    ).strip()


def normalize_url(url):
    parsed = urlparse(url.strip())
    return urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        "",
        "",
        ""
    ))


def element_text(parent, name):
    element = parent.find(name)
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def get_articles():
    articles = []
    successful_feeds = 0

    for source, url in FEEDS.items():
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = root.findall(".//item")

            if not items:
                raise ValueError("Feed senza elementi RSS")

            successful_feeds += 1
            print(
                source, "- articoli ricevuti:",
                len(items), flush=True
            )

            for item in items[:MAX_PER_FEED]:
                title = clean_text(
                    element_text(item, "title")
                )
                link = element_text(item, "link")
                description = clean_text(
                    element_text(item, "description")
                )

                if not title or not link.startswith("https://"):
                    continue

                normalized = normalize_title(title)

                if any(
                    word in normalized
                    for word in EXCLUDED
                ):
                    continue

                url_key = normalize_url(link)
                article_id = hashlib.sha256(
                    url_key.encode("utf-8")
                ).hexdigest()

                articles.append({
                    "id": article_id,
                    "title": title,
                    "url": link,
                    "description": description[:300],
                    "source": source,
                    "title_key": normalized
                })

        except Exception as error:
            print(
                "ERRORE FONTE:", source,
                str(error), flush=True
            )

    if successful_feeds == 0:
        raise RuntimeError(
            "Nessuna fonte RSS disponibile. "
            "Storico non modificato."
        )

    # Evita titoli identici tra le fonti.
    unique = []
    titles = set()

    for article in articles:
        if article["title_key"] in titles:
            continue

        titles.add(article["title_key"])
        unique.append(article)

    print(
        "NOTIZIE SELEZIONATE:",
        len(unique), flush=True
    )

    return unique


def send_discord(article):
    if not WEBHOOK:
        raise RuntimeError(
            "Secret DISCORD_WEBHOOK_GAMING mancante"
        )

    embed = {
        "title": article["title"][:256],
        "url": article["url"],
        "description": article["description"][:300],
        "color": 0x00D9D0,
        "footer": {
            "text": (
                "ARTYKO GAMING NEWS | "
                + article["source"]
            )
        },
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat()
    }

    if COVER.is_file():
        embed["image"] = {
            "url": "attachment://gaming_cover.png"
        }

        with COVER.open("rb") as image:
            response = session.post(
                WEBHOOK,
                data={
                    "payload_json": json.dumps({
                        "embeds": [embed]
                    })
                },
                files={
                    "files[0]": (
                        "gaming_cover.png",
                        image,
                        "image/png"
                    )
                },
                timeout=30
            )
    else:
        raise RuntimeError(
            "Copertina gaming_cover.png mancante"
        )

    response.raise_for_status()


def main():
    articles = get_articles()

    if not articles:
        print(
            "Nessun articolo idoneo.",
            flush=True
        )
        return

    if STATE.exists():
        seen = set(json.loads(
            STATE.read_text(encoding="utf-8")
        ))
        new_articles = [
            article for article in articles
            if article["id"] not in seen
        ]
    else:
        seen = set()
        new_articles = articles[:FIRST_RUN_LIMIT]

    selected = new_articles[:MAX_PER_RUN]

    print(
        "NOTIZIE DA PUBBLICARE:",
        len(selected), flush=True
    )

    for article in selected:
        print(
            "NOTIZIA:",
            article["source"],
            "|", article["title"],
            "|", article["url"],
            flush=True
        )

    if DRY_RUN:
        print(
            "SIMULAZIONE: nessun messaggio inviato.",
            flush=True
        )
        return

    for article in selected:
        send_discord(article)
        seen.add(article["id"])

        # Salva dopo ogni invio riuscito.
        STATE.write_text(
            json.dumps(sorted(seen), indent=2),
            encoding="utf-8"
        )
        time.sleep(2)

    print(
        "Storico GAMING aggiornato.",
        flush=True
    )


if __name__ == "__main__":
    main()
