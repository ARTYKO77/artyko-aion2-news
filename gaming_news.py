
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

# ==========================================
# ARTYKO GAMING NEWS V4
# ANNUNCI, UPDATE, DLC E GAMEPLAY
# ==========================================

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

MAX_PER_FEED = 40
FIRST_RUN_LIMIT = 3
MAX_PER_RUN = 3

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-Gaming-News/4.0"
})

# Tipologie che non vogliamo pubblicare.
EXCLUDED_TYPES = (
    "recensione", "review", "guida", "guide",
    "walkthrough", "soluzione", "trucchi",
    "offerta", "offerte", "sconto", "sconti",
    "coupon", "preorder", "pre order",
    "preordini", "compra ora", "best deals",
    "prezzo", "costa solo",
    "merchandising", "merchandise",
    "action figure", "funko pop",
    "gadget", "collezionabili",
    "magliette", "abbigliamento",
    "colonna sonora in vinile",
    "artbook",
)

# Cinema, serie TV e adattamenti.
NON_GAMING_TERMS = (
    "al cinema", "nelle sale",
    "box office", "botteghino",
    "film", "movie", "movies",
    "cinema", "cinematografico",
    "live action", "live-action",
    "serie tv", "serie televisiva",
    "tv series", "television series",
    "episodio della serie",
    "stagione della serie",
    "seconda stagione",
    "terza stagione",
    "quarta stagione",
    "quinta stagione",
    "adattamento televisivo",
    "adattamento cinematografico",
    "galleria di immagini",
    "regista", "sceneggiatore",
    "cast", "attore", "attrice",
    "netflix", "disney plus",
    "prime video", "hbo max",
    "paramount plus",
    "warner bros pictures",
)

NON_GAMING_CATEGORIES = (
    "cinema", "movies", "film",
    "televisione", "television",
    "tv", "serie tv", "streaming",
    "anime", "comics", "fumetti",
)

# Notizie commerciali, statistiche e record.
COMMERCIAL_TERMS = (
    "copie vendute",
    "milioni di copie",
    "milioni di giocatori",
    "record di giocatori",
    "record di utenti",
    "record di vendite",
    "record di incassi",
    "vendite", "fatturato",
    "ricavi", "profitti",
    "risultati finanziari",
    "risultati commerciali",
    "mercato azionario",
    "azioni in borsa",
    "quotazione in borsa",
    "ha venduto",
    "piu venduto",
    "piu venduti",
    "best selling",
    "sales figures",
    "sales record",
    "copies sold",
    "million players",
    "million copies",
    "player count",
    "concurrent players",
    "revenue", "earnings",
    "financial results",
    "stock price",
    "share price",
)

# Segnali di vere novità videoludiche.
NEWS_TERMS = (
    "annunciato", "annunciata",
    "annuncia", "annunciano",
    "announced", "announcement",
    "presentato", "presentata",
    "presenta", "revealed",
    "reveal", "svelato", "svelata",
    "confermato", "confermata",
    "confirmed",
    "nuovo gioco", "nuova ip",
    "new game", "new title",
    "in sviluppo", "in development",
    "uscira", "uscita",
    "release date", "release window",
    "data di lancio", "data di uscita",
    "lancio", "launch",
    "disponibile", "available",
    "arriva su", "arrivera su",
    "coming to", "coming soon",
    "gameplay", "gameplay trailer",
    "trailer di gioco",
    "trailer del gioco",
    "game trailer",
    "nuovo trailer", "new trailer",
    "aggiornamento", "aggiornamenti",
    "update", "updates",
    "patch", "hotfix",
    "bug fix", "bugfix",
    "correzioni", "miglioramenti",
    "nuove funzionalita",
    "new features",
    "nuova modalita", "new mode",
    "nuova mappa", "new map",
    "nuovo personaggio", "new character",
    "nuova classe", "new class",
    "espansione", "expansion",
    "dlc", "contenuti aggiuntivi",
    "nuovi contenuti", "new content",
    "stagione di gioco",
    "season update", "season pass",
    "early access", "accesso anticipato",
    "beta", "playtest",
    "demo", "roadmap",
    "crossplay", "cross play",
    "cross progression",
    "server update",
    "server test",
    "maintenance update",
)

GAMING_TERMS = (
    "videogioco", "videogiochi",
    "videogame", "video game",
    "gaming", "gameplay",
    "playstation", "ps5", "ps4",
    "xbox", "nintendo", "switch",
    "steam", "game pass",
    "epic games", "ubisoft",
    "activision", "blizzard",
    "bethesda", "capcom",
    "fromsoftware", "bandai namco",
    "square enix", "cd projekt",
    "rockstar", "mmorpg",
    "multiplayer", "dlc",
    "gta", "call of duty",
    "battlefield", "resident evil",
    "final fantasy", "monster hunter",
    "assassin s creed", "elden ring",
    "warframe", "escape from tarkov",
    "aion 2", "wardogs",
    "world of warcraft", "minecraft",
    "fortnite", "pokemon",
    "zelda", "mario kart",
    "super mario", "silent hill",
    "the witcher", "crimson desert",
    "phantom blade", "gears of war",
    "state of decay", "tomb raider",
    "mafia", "forza horizon",
    "stalker", "cyberpunk",
    "bioshock", "halo",
    "borderlands", "diablo",
    "overwatch", "destiny",
    "arc raiders", "marathon",
    "fable", "starfield",
    "hollow knight",
    "metal gear", "death stranding",
)

GAMING_CATEGORIES = (
    "videogiochi", "videogames",
    "video games", "gaming",
    "games", "playstation",
    "xbox", "nintendo",
    "pc gaming", "esports",
    "mmorpg",
)


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return " ".join(value.split())


def normalize(value):
    value = unicodedata.normalize(
        "NFKD", value or ""
    )
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )
    return re.sub(
        r"[^a-z0-9]+", " ", value.lower()
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
        "", "", ""
    ))


def element_text(parent, name):
    element = parent.find(name)
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def get_categories(item):
    result = []

    for category in item.findall("category"):
        text = clean_text(
            "".join(category.itertext())
        )
        if text:
            result.append(text)

    return result


def is_gaming_article(title, description, categories, source):
    title_key = normalize(title)
    description_key = normalize(description)
    categories_key = normalize(
        " ".join(categories)
    )

    # Esclusioni assolute nel titolo.
    if has_term(title_key, EXCLUDED_TYPES):
        return False, "tipologia esclusa"

    if has_term(title_key, NON_GAMING_TERMS):
        return False, "cinema/TV"

    if has_term(title_key, COMMERCIAL_TERMS):
        return False, "vendite/record"

    # Le categorie non gaming prevalgono.
    if has_term(
        categories_key, NON_GAMING_CATEGORIES
    ):
        return False, "categoria non gaming"

    # Anche la descrizione può rivelare
    # che si tratta di cinema o merchandising.
    if has_term(
        description_key, NON_GAMING_TERMS
    ):
        return False, "descrizione cinema/TV"

    if has_term(
        description_key, COMMERCIAL_TERMS
    ):
        return False, "descrizione commerciale"

    if has_term(
        description_key, EXCLUDED_TYPES
    ):
        return False, "descrizione esclusa"

    # Richiediamo una novità concreta nel titolo.
    if not has_term(title_key, NEWS_TERMS):
        return False, "non e una novita gaming"

    # GameSpot è un feed gaming dedicato.
    if source == "GameSpot":
        return True, "novita da GameSpot"

    # IGN richiede anche un segnale gaming.
    if has_term(
        categories_key, GAMING_CATEGORIES
    ):
        return True, "novita categoria gaming"

    if has_term(title_key, GAMING_TERMS):
        return True, "novita titolo gaming"

    return False, "nessun riferimento gaming"


def get_articles():
    articles = []
    successful_feeds = 0

    for source, feed_url in FEEDS.items():
        try:
            response = session.get(
                feed_url, timeout=25
            )
            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = root.findall(".//item")

            if not items:
                raise ValueError(
                    "Feed RSS senza articoli"
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
                link = element_text(item, "link")
                description = clean_text(
                    element_text(item, "description")
                )
                categories = get_categories(item)

                if not title or not link.startswith(
                    "https://"
                ):
                    continue

                allowed, reason = is_gaming_article(
                    title, description,
                    categories, source
                )

                print(
                    "AMMESSA:" if allowed else "SCARTATA:",
                    reason,
                    "|", title[:110],
                    flush=True
                )

                if not allowed:
                    continue

                title_key = normalize(title)
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
                    "title_key": title_key
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
            "Nessun feed disponibile. "
            "Storico non modificato."
        )

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

    if not COVER.is_file():
        raise RuntimeError(
            "Copertina gaming_cover.png mancante"
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
        ).isoformat(),
        "image": {
            "url": "attachment://gaming_cover.png"
        }
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
