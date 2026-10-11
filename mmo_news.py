
import os
import re
import json
import time
import hashlib
import html
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import requests
import feedparser

# =====================================
# ARTYKO MMO NEWS
# =====================================

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "mmo_seen_articles.json"
COVER_FILE = BASE_DIR / "mmo_cover.png"

WEBHOOK = os.getenv("DISCORD_WEBHOOK_MMO", "")
DRY_RUN = os.getenv(
    "MMO_DRY_RUN", "true"
).lower() != "false"

FEEDS = {
    "MMORPG.com": "https://www.mmorpg.com/rss",
    "Massively Overpowered": "https://massivelyop.com/feed/",
}

MAX_PER_RUN = 3
MAX_FEED_ITEMS = 30

EXCLUDED_WORDS = (
    "review",
    "recensione",
    "buyer's guide",
    "shopping guide",
    "best deals",
    "coupon",
    "discount code",
)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 ARTYKO-MMO-News/1.0"
})


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return " ".join(value.split())


def article_key(url):
    parts = urlsplit(url.strip())

    normalized = urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/"),
        "",
        ""
    ))

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def load_seen():
    if not STATE_FILE.exists():
        return set()

    data = json.loads(
        STATE_FILE.read_text(encoding="utf-8")
    )

    return set(data)


def save_seen(seen):
    STATE_FILE.write_text(
        json.dumps(
            sorted(seen),
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def fetch_articles():
    articles = []
    successful_feeds = 0

    for source, feed_url in FEEDS.items():
        try:
            response = session.get(
                feed_url,
                timeout=25
            )
            response.raise_for_status()

            feed = feedparser.parse(response.content)

            if not feed.entries:
                raise ValueError(
                    "Nessun articolo trovato nel feed"
                )

            successful_feeds += 1

            print(
                f"{source}: "
                f"{len(feed.entries)} articoli ricevuti",
                flush=True
            )

            for entry in feed.entries[:MAX_FEED_ITEMS]:
                title = clean_text(
                    entry.get("title", "")
                )

                url = entry.get("link", "").strip()

                description = clean_text(
                    entry.get("summary", "")
                )

                if not title or not url.startswith(
                    ("https://", "http://")
                ):
                    continue

                lower_title = title.lower()

                if any(
                    word in lower_title
                    for word in EXCLUDED_WORDS
                ):
                    continue

                articles.append({
                    "id": article_key(url),
                    "title": title,
                    "url": url,
                    "description": description[:350],
                    "source": source
                })

        except Exception as error:
            print(
                f"ERRORE FONTE {source}: {error}",
                flush=True
            )

    if successful_feeds == 0:
        raise RuntimeError(
            "Nessun feed MMO funzionante. "
            "Controllare gli URL delle fonti."
        )

    unique_articles = []
    known_ids = set()

    for article in articles:
        if article["id"] in known_ids:
            continue

        known_ids.add(article["id"])
        unique_articles.append(article)

    print(
        f"Totale notizie selezionate: "
        f"{len(unique_articles)}",
        flush=True
    )

    return unique_articles


def publish_article(article):
    if not WEBHOOK:
        raise RuntimeError(
            "Secret DISCORD_WEBHOOK_MMO mancante"
        )

    if not COVER_FILE.is_file():
        raise RuntimeError(
            "Copertina mmo_cover.png mancante"
        )

    embed = {
        "title": article["title"][:256],
        "url": article["url"],
        "description": article["description"][:350],
        "color": 0x00D9B5,
        "image": {
            "url": "attachment://mmo_cover.png"
        },
        "footer": {
            "text": (
                "ARTYKO MMO NEWS | "
                + article["source"]
            )
        },
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat()
    }

    payload = {
        "username": "ARTYKO MMO NEWS",
        "embeds": [embed]
    }

    with COVER_FILE.open("rb") as image:
        response = session.post(
            WEBHOOK,
            data={
                "payload_json": json.dumps(payload)
            },
            files={
                "files[0]": (
                    "mmo_cover.png",
                    image,
                    "image/png"
                )
            },
            timeout=30
        )

    response.raise_for_status()


def main():
    print(
        "=== ARTYKO MMO NEWS ===",
        flush=True
    )

    print(
        "Modalita simulazione:",
        DRY_RUN,
        flush=True
    )

    articles = fetch_articles()
    seen = load_seen()

    new_articles = [
        article for article in articles
        if article["id"] not in seen
    ]

    # Primo avvio: solo tre articoli.
    selected = new_articles[:MAX_PER_RUN]

    print(
        f"Nuove notizie trovate: "
        f"{len(new_articles)}",
        flush=True
    )

    print(
        f"Notizie selezionate: "
        f"{len(selected)}",
        flush=True
    )

    for article in selected:
        print(
            f"[{article['source']}] "
            f"{article['title']}",
            flush=True
        )
        print(
            article["url"],
            flush=True
        )

    if DRY_RUN:
        print(
            "TEST COMPLETATO: "
            "nessun messaggio inviato a Discord.",
            flush=True
        )
        return

    for article in selected:
        publish_article(article)

        seen.add(article["id"])
        save_seen(seen)

        print(
            f"PUBBLICATO: {article['title']}",
            flush=True
        )

        time.sleep(2)

    print(
        "ARTYKO MMO NEWS: esecuzione completata.",
        flush=True
    )


if __name__ == "__main__":
    main()
