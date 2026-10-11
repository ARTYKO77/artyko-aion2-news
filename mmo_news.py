
import os
import re
import json
import time
import html
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import requests
import feedparser

# =====================================
# ARTYKO MMO NEWS - VERSIONE 3
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
MAX_FEED_ITEMS = 50

# Giochi MMORPG e mondi online persistenti.
MMO_KEYWORDS = (
    "mmorpg",
    "mmo",
    "world of warcraft",
    "wow classic",
    "warcraft",
    "aion",
    "final fantasy xiv",
    "ffxiv",
    "guild wars",
    "elder scrolls online",
    "black desert",
    "runescape",
    "old school runescape",
    "ashes of creation",
    "chrono odyssey",
    "archeage",
    "throne and liberty",
    "lost ark",
    "new world",
    "eve online",
    "albion online",
    "blade and soul",
    "blade & soul",
    "maplestory",
    "lineage",
    "blue protocol",
    "pax dei",
    "star citizen",
    "pantheon",
    "everquest",
    "dune awakening",
    "dune: awakening",
    "once human",
    "soulframe",
    "the quinfall",
    "corepunk",
    "project gorgon",
    "tower of fantasy",
    "the first descendant",
    "destiny 2",
    "warframe",
    "fractured online",
)

# Contenuti da evitare.
EXCLUDED_KEYWORDS = (
    "sea of thieves",
    "fortnite",
    "valorant",
    "counter-strike",
    "call of duty",
    "apex legends",
    "overwatch",
    "league of legends",
    "marvel rivals",
    "review",
    "recensione",
    "buyer's guide",
    "shopping guide",
    "best deals",
    "coupon",
    "discount code",
)

GENERIC_MMO_TERMS = (
    "mmorpg",
    "massively multiplayer",
    "massively-multiplayer",
    "new mmo",
    "upcoming mmo",
    "sandbox mmo",
    "fantasy mmo",
)

ANNOUNCEMENT_TERMS = (
    "new online rpg",
    "new online game",
    "new multiplayer rpg",
)

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-MMO-News/3.0"
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


def contains_keyword(text, keyword):
    # Evita corrispondenze dentro altre parole.
    pattern = (
        r"(?<!\w)"
        + re.escape(keyword)
        + r"(?!\w)"
    )

    return re.search(pattern, text) is not None


def contains_any(text, keywords):
    return any(
        contains_keyword(text, keyword)
        for keyword in keywords
    )


def is_relevant(article):
    title = article["title"].lower()
    description = article["description"].lower()

    # Esclude argomenti indesiderati.
    if contains_any(title, EXCLUDED_KEYWORDS):
        return False

    # I titoli che nominano MMORPG noti
    # hanno la priorita'.
    if contains_any(title, MMO_KEYWORDS):
        return True

    # Intercetta annunci di MMORPG nuovi
    # anche senza un nome gia' conosciuto.
    if contains_any(title, GENERIC_MMO_TERMS):
        return True

    # La descrizione e' solo un supporto.
    if (
        contains_any(title, ANNOUNCEMENT_TERMS)
        and contains_any(
            description,
            GENERIC_MMO_TERMS
        )
    ):
        return True

    return False


def fetch_articles():
    by_source = {}
    successful_feeds = 0

    for source, feed_url in FEEDS.items():
        by_source[source] = []

        try:
            response = session.get(
                feed_url,
                timeout=25
            )
            response.raise_for_status()

            feed = feedparser.parse(
                response.content
            )

            if not feed.entries:
                raise ValueError(
                    "Feed senza articoli"
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

                url = entry.get(
                    "link", ""
                ).strip()

                description = clean_text(
                    entry.get("summary", "")
                )

                if not title or not url.startswith(
                    ("https://", "http://")
                ):
                    continue

                article = {
                    "id": article_key(url),
                    "title": title,
                    "url": url,
                    "description": description[:350],
                    "source": source
                }

                if is_relevant(article):
                    by_source[source].append(
                        article
                    )

            print(
                f"{source}: "
                f"{len(by_source[source])} "
                "notizie pertinenti",
                flush=True
            )

        except Exception as error:
            print(
                f"ERRORE FONTE {source}: "
                f"{error}",
                flush=True
            )

    if successful_feeds == 0:
        raise RuntimeError(
            "Nessuna fonte MMO disponibile"
        )

    # Alterna gli articoli delle fonti.
    combined = []

    max_length = max(
        (
            len(items)
            for items in by_source.values()
        ),
        default=0
    )

    for index in range(max_length):
        for source in FEEDS:
            items = by_source[source]

            if index < len(items):
                combined.append(
                    items[index]
                )

    # Elimina gli URL duplicati.
    unique = []
    known = set()

    for article in combined:
        if article["id"] in known:
            continue

        known.add(article["id"])
        unique.append(article)

    print(
        "Notizie MMO selezionate:",
        len(unique),
        flush=True
    )

    return unique


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
        "description": (
            article["description"][:350]
        ),
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
                "payload_json": json.dumps(
                    payload
                )
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
        "=== ARTYKO MMO NEWS V3 ===",
        flush=True
    )

    print(
        "Simulazione:",
        DRY_RUN,
        flush=True
    )

    articles = fetch_articles()
    seen = load_seen()

    new_articles = [
        article
        for article in articles
        if article["id"] not in seen
    ]

    selected = new_articles[:MAX_PER_RUN]

    print(
        "Nuove notizie:",
        len(new_articles),
        flush=True
    )

    print(
        "Notizie pronte:",
        len(selected),
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
            "SIMULAZIONE COMPLETATA. "
            "Nessun messaggio pubblicato.",
            flush=True
        )
        return

    for article in selected:
        publish_article(article)

        seen.add(article["id"])
        save_seen(seen)

        print(
            "PUBBLICATO:",
            article["title"],
            flush=True
        )

        time.sleep(2)

    print(
        "ARTYKO MMO NEWS completato.",
        flush=True
    )


if __name__ == "__main__":
    main()
