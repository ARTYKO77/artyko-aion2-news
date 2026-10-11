
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


# ============================================================
# ARTYKO SEA OF THIEVES NEWS
# Fonte: Steam News API - Sea of Thieves (appid 1172620)
# ============================================================

APP_ID = 1172620

STEAM_API = (
    "https://api.steampowered.com/"
    "ISteamNews/GetNewsForApp/v2/"
)

WEBHOOK = os.getenv("DISCORD_WEBHOOK_SEAOFTHIEVES", "").strip()

DRY_RUN = os.getenv(
    "SEAOFTHIEVES_DRY_RUN", "true"
).lower() not in ("false", "0", "no")

HISTORY_FILE = Path("seaofthieves_seen_articles.json")
COVER_FILE = Path("seaofthieves_cover.png")

MAX_ARTICLES = 2
FETCH_COUNT = 50
HISTORY_LIMIT = 500

# Solo annunci pubblicati sul canale ufficiale Steam.
ALLOWED_FEEDS = {
    "steam_community_announcements",
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "ARTYKO-SeaOfThieves-News/1.0",
    "Accept": "application/json",
})


def clean_text(value):
    """Rimuove markup e normalizza il testo."""
    value = html.unescape(str(value or ""))

    value = re.sub(
        r"\[/?[a-zA-Z][^\]]*\]",
        " ",
        value,
    )

    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def load_history():
    if not HISTORY_FILE.exists():
        return set()

    try:
        data = json.loads(
            HISTORY_FILE.read_text(encoding="utf-8")
        )

        if isinstance(data, list):
            return set(map(str, data))

        if isinstance(data, dict):
            return set(
                map(str, data.get("seen", []))
            )

    except (OSError, ValueError) as error:
        print(f"Errore lettura storico: {error}")
        raise

    raise ValueError("Formato storico non valido.")


def save_history(seen):
    values = sorted(seen)[-HISTORY_LIMIT:]

    temporary = HISTORY_FILE.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            {"seen": values},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(HISTORY_FILE)


def fetch_news():
    params = {
        "appid": APP_ID,
        "count": FETCH_COUNT,
        "maxlength": 1000,
    }

    response = SESSION.get(
        STEAM_API,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    articles = data.get(
        "appnews", {}
    ).get("newsitems", [])

    if not isinstance(articles, list):
        raise ValueError("Risposta Steam non valida.")

    print(f"Articoli ricevuti da Steam: {len(articles)}")

    return articles


def is_official(article):
    if article.get("feedname") not in ALLOWED_FEEDS:
        return False

    if int(article.get("appid", APP_ID)) != APP_ID:
        return False

    title = clean_text(article.get("title"))

    if not title:
        return False

    return bool(article.get("gid"))


def article_id(article):
    return str(article["gid"])


def article_url(article):
    # Manteniamo il collegamento restituito da Steam.
    url = str(article.get("url", "")).strip()

    parsed = urlparse(url)

    if parsed.scheme != "https":
        return ""

    if not (
        parsed.hostname == "steampowered.com"
        or parsed.hostname.endswith(".steampowered.com")
        or parsed.hostname == "steamcommunity.com"
        or parsed.hostname.endswith(".steamcommunity.com")
        or parsed.hostname == "akamaihd.net"
        or parsed.hostname.endswith(".akamaihd.net")
    ):
        return ""

    return url


def format_date(timestamp):
    try:
        date = datetime.fromtimestamp(
            int(timestamp),
            tz=timezone.utc,
        )
        return date.isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def make_embed(article):
    title = clean_text(article.get("title"))
    description = clean_text(
        article.get("contents")
    )

    if not description:
        description = (
            "Nuovo annuncio ufficiale di Sea of Thieves. "
            "Apri l'articolo per tutti i dettagli."
        )

    description = description[:900]

    embed = {
        "title": f"🏴‍☠️ {title}"[:256],
        "url": article_url(article),
        "description": description,
        "color": 0x21D8C3,
        "footer": {
            "text": (
                "ARTYKO • Sea of Thieves News "
                "• Fonte ufficiale Steam"
            )
        },
    }

    timestamp = format_date(
        article.get("date")
    )

    if timestamp:
        embed["timestamp"] = timestamp

    if COVER_FILE.exists():
        embed["image"] = {
            "url": "attachment://seaofthieves_cover.png"
        }

    return embed


def publish_article(article):
    if not WEBHOOK:
        raise RuntimeError(
            "Secret DISCORD_WEBHOOK_SEAOFTHIEVES mancante."
        )

    embed = make_embed(article)

    payload = {
        "username": "ARTYKO SEA OF THIEVES NEWS",
        "embeds": [embed],
        "allowed_mentions": {
            "parse": [],
        },
    }

    if COVER_FILE.exists():
        with COVER_FILE.open("rb") as cover:
            response = requests.post(
                WEBHOOK,
                data={
                    "payload_json": json.dumps(
                        payload,
                        ensure_ascii=False,
                    )
                },
                files={
                    "files[0]": (
                        "seaofthieves_cover.png",
                        cover,
                        "image/png",
                    )
                },
                timeout=45,
            )
    else:
        response = requests.post(
            WEBHOOK,
            json=payload,
            timeout=45,
        )

    if response.status_code == 429:
        raise RuntimeError(
            "Discord ha imposto un limite temporaneo."
        )

    response.raise_for_status()

    if response.status_code not in (200, 204):
        raise RuntimeError(
            f"Risposta Discord inattesa: "
            f"{response.status_code}"
        )


def main():
    print("=" * 55)
    print("ARTYKO SEA OF THIEVES NEWS")
    print(
        "Modalità:",
        "TEST - nessuna pubblicazione"
        if DRY_RUN
        else "PUBBLICAZIONE REALE",
    )
    print("=" * 55)

    articles = fetch_news()

    official = [
        article
        for article in articles
        if is_official(article)
        and article_url(article)
    ]

    print(f"Annunci ufficiali validi: {len(official)}")

    # Ordine cronologico, dal più vecchio al più recente.
    official.sort(
        key=lambda item: int(item.get("date", 0))
    )

    seen = load_history()

    # Alla prima esecuzione reale non inviamo
    # decine di notizie vecchie.
    if not HISTORY_FILE.exists():
        print(
            "Prima esecuzione: "
            "inizializzazione dello storico."
        )

        if DRY_RUN:
            print(
                "TEST: nessuno storico verrà salvato."
            )
            for article in official[-5:]:
                print(
                    "[ANTEPRIMA]",
                    clean_text(article.get("title")),
                )
            return

        save_history({
            article_id(article)
            for article in official
        })

        print(
            "Storico inizializzato. "
            "Nessun vecchio articolo pubblicato."
        )
        return

    new_articles = [
        article
        for article in official
        if article_id(article) not in seen
    ]

    print(f"Nuove notizie: {len(new_articles)}")

    selected = new_articles[:MAX_ARTICLES]

    for article in selected:
        title = clean_text(article.get("title"))

        if DRY_RUN:
            print(f"[TEST] {title}")
            print(f"       {article_url(article)}")
            continue

        print(f"Pubblicazione: {title}")

        publish_article(article)

        seen.add(article_id(article))
        save_history(seen)

        print("Pubblicazione riuscita.")

        time.sleep(2)

    if not selected:
        print("Nessuna nuova notizia da pubblicare.")

    print("Controllo completato.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"ERRORE: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
