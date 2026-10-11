
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

# =========================================
# ARTYKO GAMING NEWS - V2
# FILTRO GAMING + PROTEZIONE CONTENUTI
# =========================================

BASE_DIR = Path(__file__).resolve().parent
STATE = BASE_DIR / "gaming_seen_articles.json"
COVER = BASE_DIR / "gaming_cover.png"

WEBHOOK = os.getenv("DISCORD_WEBHOOK_GAMING", "")
DRY_RUN = os.getenv(
    "GAMING_DRY_RUN", "true"
).lower() != "false"

FEEDS = {
    "IGN Italia": "https://it.ign.com/feed.xml",
    "GameSpot": "https://www.gamespot.com/feeds/game-news/"
}

MAX_PER_FEED = 30
FIRST_RUN_LIMIT = 3
MAX_PER_RUN = 3

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-Gaming-News/2.0"
})

EXCLUDED = (
    "recensione", "review", "guida",
    "guide", "soluzione", "walkthrough",
    "trucchi", "offerta", "sconto",
    "coupon", "preorder", "pre order",
    "compra ora", "migliori offerte",
    "best deals"
)

# Argomenti tipicamente estranei ai videogiochi.
NON_GAMING = (
    "al cinema",
    "nelle sale",
    "box office",
    "incassi al botteghino",
    "trailer ufficiale del film",
    "nuovo film",
    "film horror",
    "film d azione",
    "galleria di immagini",
    "stagione della serie",
    "episodio della serie",
    "serie tv",
    "serie televisiva",
    "netflix",
    "prime video",
    "disney plus",
    "hbo max",
    "warner bros pictures",
)

# Termini che indicano contenuti gaming.
GAMING_TERMS = (
    "videogioco",
    "videogiochi",
    "videogame",
    "video game",
    "gaming",
    "gameplay",
    "gioco",
    "giochi",
    "giocatori",
    "playstation",
    "ps5",
    "ps4",
    "xbox",
    "nintendo",
    "switch",
    "steam",
    "pc gaming",
    "computer gaming",
    "game pass",
    "epic games",
    "ubisoft",
    "electronic arts",
    "activision",
    "blizzard",
    "bethesda",
    "capcom",
    "fromsoftware",
    "bandai namco",
    "square enix",
    "cd projekt",
    "rockstar games",
    "unreal engine",
    "mmorpg",
    "rpg",
    "fps",
    "dlc",
    "patch",
    "aggiornamento",
    "early access",
    "accesso anticipato",
    "multiplayer",
    "esport",
    "e sport",
    "gta",
    "call of duty",
    "battlefield",
    "resident evil",
    "final fantasy",
    "monster hunter",
    "assassin s creed",
    "elden ring",
    "warframe",
    "escape from tarkov",
    "aion 2",
    "wardogs",
    "world of warcraft",
    "minecraft",
    "fortnite",
    "pokemon",
    "zelda",
    "mario kart",
    "super mario",
    "silent hill",
    "the witcher",
    "crimson desert",
    "phantom blade",
    "gears of war",
)

# Categorie RSS chiaramente gaming.
GAMING_CATEGORIES = (
    "videogiochi",
    "video games",
    "videogames",
    "gaming",
    "games",
    "playstation",
    "xbox",
    "nintendo",
    "pc gaming",
    "esports",
    "mmorpg",
)

# Categorie RSS chiaramente non gaming.
NON_GAMING_CATEGORIES = (
    "cinema",
    "movies",
    "film",
    "televisione",
    "television",
    "tv",
    "serie tv",
    "streaming",
    "anime",
    "comics",
    "fumetti",
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


def has_term(text, terms):
    return any(
        re.search(
            r"(?<![a-z0-9])"
            + re.escape(term)
            + r"(?![a-z0-9])",
            text,
        )
        for term in terms
    )


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


def get_categories(item):
    categories = []

    for category in item.findall("category"):
        text = clean_text(
            "".join(category.itertext())
        )
        if text:
            categories.append(text)

    return categories


def is_gaming_article(title, description, categories, source):
    title_key = normalize_title(title)
    description_key = normalize_title(description)
    categories_key = normalize_title(
        " ".join(categories)
    )

    combined = f"{title_key} {description_key}"

    if has_term(title_key, EXCLUDED):
        return False, "tipologia esclusa"

    gaming_category = has_term(
        categories_key, GAMING_CATEGORIES
    )
    non_gaming_category = has_term(
        categories_key, NON_GAMING_CATEGORIES
    )

    gaming_title = has_term(
        title_key, GAMING_TERMS
    )
    gaming_description = has_term(
        description_key, GAMING_TERMS
    )

    non_gaming_content = has_term(
        combined, NON_GAMING
    )

    # Categoria esplicitamente non gaming:
    # ammettiamo solo se c'è anche una categoria
    # gaming e il titolo parla di gaming.
    if non_gaming_category and not (
        gaming_category and gaming_title
    ):
        return False, "categoria non gaming"

    # Cinema/TV senza un riferimento gaming
    # esplicito nel titolo.
    if non_gaming_content and not gaming_title:
        return False, "contenuto cinema/TV"

    # GameSpot usa un feed dedicato alle game news.
    # Resta comunque attivo il filtro negativo.
    if source == "GameSpot":
        return True, "feed gaming dedicato"

    # IGN Italia: prima le categorie.
    if gaming_category:
        return True, "categoria gaming"

    # In assenza di categorie affidabili,
    # richiediamo un riferimento gaming nel titolo.
    if gaming_title:
        return True, "titolo gaming"

    # Descrizioni generiche non bastano da sole.
    return False, "nessun segnale gaming sufficiente"


def get_articles():
    articles = []
    successful_feeds = 0

    for source, url in FEEDS.items():
        try:
            response = session.get(
                url, timeout=25
            )
            response.raise_for_status()

            root = ET.fromstring(
                response.content
            )
            items = root.findall(".//item")

            if not items:
                raise ValueError(
                    "Feed senza elementi RSS"
                )

            successful_feeds += 1

            print(
                source,
                "- articoli ricevuti:",
                len(items),
                flush=True
            )

            for item in items[:MAX_PER_FEED]:
                title = clean_text(
                    element_text(item, "title")
                )
                link = element_text(
                    item, "link"
                )
                description = clean_text(
                    element_text(item, "description")
                )
                categories = get_categories(item)

                if not title or not link.startswith(
                    "https://"
                ):
                    continue

                allowed, reason = is_gaming_article(
                    title,
                    description,
                    categories,
                    source
                )

                if not allowed:
                    print(
                        "SCARTATA:",
                        reason,
                        "|", title[:110],
                        flush=True
                    )
                    continue

                print(
                    "AMMESSA:",
                    reason,
                    "|", title[:110],
                    flush=True
                )

                normalized = normalize_title(title)
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
                "ERRORE FONTE:",
                source,
                str(error),
                flush=True
            )

    if successful_feeds == 0:
        raise RuntimeError(
            "Nessuna fonte RSS disponibile. "
            "Storico non modificato."
        )

    # Rimuove titoli identici fra le fonti.
    unique = []
    titles = set()

    for article in articles:
        if article["title_key"] in titles:
            continue

        titles.add(article["title_key"])
        unique.append(article)

    print(
        "NOTIZIE SELEZIONATE:",
        len(unique),
        flush=True
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

    if not COVER.is_file():
        raise RuntimeError(
            "Copertina gaming_cover.png mancante"
        )

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
        len(selected),
        flush=True
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

        STATE.write_text(
            json.dumps(
                sorted(seen), indent=2
            ),
            encoding="utf-8"
        )
        time.sleep(2)

    print(
        "Storico GAMING aggiornato.",
        flush=True
    )


if __name__ == "__main__":
    main()
