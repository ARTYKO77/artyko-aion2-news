
import os
import re
import json
import html
import time
import hashlib
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

import requests

# ==========================================
# ARTYKO GAMING NEWS V6
# MODALITA' EQUILIBRATA
# MAX 2 NOTIZIE AL GIORNO
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
STATE = BASE_DIR / "gaming_seen_articles.json"
COVER = BASE_DIR / "gaming_cover.png"

WEBHOOK = os.getenv("DISCORD_WEBHOOK_GAMING", "")
DRY_RUN = os.getenv(
    "GAMING_DRY_RUN", "true"
).lower() != "false"

ITALY_TZ = ZoneInfo("Europe/Rome")
DAILY_LIMIT = 2

FEEDS = {
    "IGN Italia": "https://it.ign.com/feed.xml",
    "GameSpot": "https://www.gamespot.com/feeds/game-news/",
}

MAX_PER_FEED = 40
FIRST_RUN_LIMIT = 3
MAX_PER_RUN = 2

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-Gaming-News/6.0"
})

EXCLUDED_TYPES = (
    "recensione", "review",
    "guida", "guide", "walkthrough",
    "soluzione", "trucchi",
    "offerta", "offerte",
    "sconto", "sconti", "coupon",
    "best deals", "deal",
    "preorder", "pre order",
    "preordini", "preordini aperti",
    "quanto costa", "costa solo",
    "prezzo", "price",
    "merchandising", "merchandise",
    "action figure", "funko pop",
    "gadget", "collezionabili",
    "magliette", "abbigliamento",
    "vinile", "artbook",
)

CINEMA_TV = (
    "film", "movie", "movies",
    "cinema", "cinematografico",
    "live action", "live-action",
    "serie tv", "serie televisiva",
    "tv series", "television series",
    "adattamento televisivo",
    "adattamento cinematografico",
    "episodio della serie",
    "stagione della serie",
    "seconda stagione",
    "terza stagione",
    "quarta stagione",
    "quinta stagione",
    "box office", "botteghino",
    "al cinema", "nelle sale",
    "regista", "sceneggiatore",
    "cast", "attore", "attrice",
    "netflix", "disney plus",
    "prime video", "hbo max",
    "paramount plus",
    "warner bros pictures",
    "galleria di immagini",
)

CINEMA_CATEGORIES = (
    "cinema", "movies", "film",
    "televisione", "television",
    "tv", "serie tv", "streaming",
    "anime", "comics", "fumetti",
)

COMMERCIAL = (
    "copie vendute", "copie piazzate",
    "milioni di copie",
    "milioni di giocatori",
    "milioni di utenti",
    "record di giocatori",
    "record di utenti",
    "record di vendite",
    "record di incassi",
    "vendite", "fatturato",
    "ricavi", "profitti",
    "risultati finanziari",
    "risultati commerciali",
    "ha venduto", "hanno venduto",
    "piu venduto", "piu venduti",
    "best selling", "copies sold",
    "million players", "million copies",
    "player count", "concurrent players",
    "revenue", "earnings",
    "financial results",
    "stock price", "share price",
    "merchandising ufficiale",
)

NEWS_TERMS = (
    "annuncia", "annunciato",
    "annunciata", "annunciati",
    "annunciate", "announced",
    "announcement",
    "presenta", "presentato",
    "presentata", "revealed",
    "reveal", "svelato", "svelata",
    "confermato", "confermata",
    "confirmed",
    "nuovo gioco", "nuova ip",
    "new game", "new title",
    "in sviluppo", "in development",
    "uscita", "uscira", "uscite",
    "release date", "release window",
    "data di lancio", "data di uscita",
    "lancio", "launch",
    "disponibile", "available",
    "arriva", "arrivera", "arrivano",
    "coming to", "coming soon",
    "gameplay", "trailer",
    "mostrato", "mostrata",
    "shown", "first look",
    "aggiornamento", "aggiornamenti",
    "aggiorna", "aggiornato",
    "aggiornata", "update", "updates",
    "patch", "hotfix",
    "bug fix", "bugfix",
    "risolve", "corregge",
    "correzioni", "miglioramenti",
    "improvements", "fixes",
    "nuova modalita", "new mode",
    "nuova mappa", "new map",
    "nuovo personaggio", "new character",
    "nuova classe", "new class",
    "nuova espansione",
    "espansione", "expansion",
    "dlc", "contenuti aggiuntivi",
    "nuovi contenuti", "new content",
    "season update", "season pass",
    "early access", "accesso anticipato",
    "beta", "playtest", "demo",
    "roadmap", "crossplay",
    "cross play", "cross progression",
    "server update", "maintenance",
    "post lancio", "post launch",
    "upgrade", "remaster",
    "remastered",
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
    "hell is us", "the talos principle",
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
        value = clean_text(
            "".join(category.itertext())
        )
        if value:
            result.append(value)

    return result


def is_gaming_article(title, description, categories, source):
    title_key = normalize(title)
    description_key = normalize(description)
    category_keys = [
        normalize(category)
        for category in categories
    ]

    if has_term(title_key, EXCLUDED_TYPES):
        return False, "tipologia esclusa"

    if has_term(title_key, CINEMA_TV):
        return False, "cinema/TV"

    if has_term(title_key, COMMERCIAL):
        return False, "vendite/record/merchandising"

    if any(
        has_term(category, CINEMA_CATEGORIES)
        for category in category_keys
    ):
        return False, "categoria cinema/TV"

    if not has_term(title_key, NEWS_TERMS):
        return False, "non e una novita gaming"

    has_gaming_category = any(
        has_term(category, GAMING_CATEGORIES)
        for category in category_keys
    )

    has_gaming_title = has_term(
        title_key, GAMING_TERMS
    )

    if not (
        source == "GameSpot"
        or has_gaming_category
        or has_gaming_title
    ):
        return False, "nessun riferimento gaming"

    if (
        not has_gaming_title
        and has_term(description_key, CINEMA_TV)
    ):
        return False, "descrizione cinema/TV"

    if source == "GameSpot":
        return True, "novita GameSpot"

    if has_gaming_category:
        return True, "novita categoria gaming"

    return True, "novita titolo gaming"


def load_state():
    if not STATE.exists():
        return {
            "seen": [],
            "daily_counts": {}
        }

    data = json.loads(
        STATE.read_text(encoding="utf-8")
    )

    # Compatibilita' con il vecchio storico V5.
    if isinstance(data, list):
        return {
            "seen": data,
            "daily_counts": {}
        }

    if isinstance(data, dict):
        return {
            "seen": data.get("seen", []),
            "daily_counts": data.get(
                "daily_counts", {}
            )
        }

    raise RuntimeError(
        "Formato storico non valido."
    )


def save_state(state):
    STATE.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def today_italy():
    return datetime.now(
        ITALY_TZ
    ).date().isoformat()


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
    state = load_state()

    seen = set(state["seen"])
    daily_counts = state["daily_counts"]

    today = today_italy()
    published_today = int(
        daily_counts.get(today, 0)
    )

    remaining = max(
        0,
        DAILY_LIMIT - published_today
    )

    print("=" * 42)
    print("ARTYKO GAMING NEWS V6")
    print("=" * 42)
    print("Data italiana:", today)
    print("Pubblicate oggi:", published_today)
    print("Limite giornaliero:", DAILY_LIMIT)
    print("Post disponibili:", remaining)
    print("Simulazione:", DRY_RUN)

    if remaining == 0:
        print(
            "Limite giornaliero raggiunto."
        )
        print(
            "Nessuna nuova pubblicazione."
        )
        return

    articles = get_articles()

    if not articles:
        print(
            "Nessun articolo idoneo.",
            flush=True
        )
        return

    if STATE.exists():
        new_articles = [
            article for article in articles
            if article["id"] not in seen
        ]
    else:
        new_articles = articles[
            :FIRST_RUN_LIMIT
        ]

    selected = new_articles[
        :min(MAX_PER_RUN, remaining)
    ]

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

        # Conteggio sulla data italiana effettiva
        # del momento di pubblicazione.
        publish_date = today_italy()

        daily_counts[publish_date] = (
            int(
                daily_counts.get(
                    publish_date, 0
                )
            ) + 1
        )

        # Mantiene solo gli ultimi 30 giorni
        # dei contatori giornalieri.
        recent_dates = sorted(
            daily_counts.keys()
        )[-30:]

        daily_counts = {
            day: daily_counts[day]
            for day in recent_dates
        }

        state["seen"] = sorted(seen)
        state["daily_counts"] = daily_counts

        save_state(state)

        print(
            "Pubblicata:",
            article["title"],
            "| Totale oggi:",
            daily_counts[publish_date],
            flush=True
        )

        time.sleep(2)

    print(
        "Storico GAMING aggiornato.",
        flush=True
    )


if __name__ == "__main__":
    main()
