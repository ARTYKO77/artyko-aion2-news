
import os
import re
import json
import time
import html
import hashlib
import unicodedata
import requests

from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

# ARTYKO | WARFRAME NEWS
# Fonti: Steam + sito ufficiale Warframe

APP_ID = 230410
STEAM_API = (
    "https://api.steampowered.com/"
    "ISteamNews/GetNewsForApp/v2/"
)
OFFICIAL_URL = "https://www.warframe.com/en/news"

BASE_DIR = Path(__file__).resolve().parent
STATE = BASE_DIR / "warframe_seen_articles.json"

WEBHOOK = os.getenv(
    "DISCORD_WEBHOOK_WARFRAME", ""
).strip()

DRY_RUN = os.getenv(
    "WARFRAME_DRY_RUN", "true"
).lower() != "false"

FIRST_RUN_LIMIT = 3

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-Warframe-News/1.0"
})


def clean_text(value):
    value = re.sub(r"\[/?[^\]]+\]", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def title_key(title):
    title = unicodedata.normalize("NFKD", title)
    title = "".join(
        c for c in title
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]", "", title.lower())


def article_id(title):
    return hashlib.sha256(
        title_key(title).encode("utf-8")
    ).hexdigest()


def get_steam():
    response = session.get(
        STEAM_API,
        params={
            "appid": APP_ID,
            "count": 100,
            "maxlength": 0,
            "format": "json"
        },
        timeout=25
    )
    response.raise_for_status()

    items = response.json().get(
        "appnews", {}
    ).get("newsitems", [])

    articles = []

    for item in items:
        if item.get("feed_type") != 1:
            continue

        title = clean_text(item.get("title", ""))
        if not title:
            continue

        url = item.get("url", "")
        if not url.startswith("https://"):
            continue

        articles.append({
            "id": article_id(title),
            "title": title,
            "url": url,
            "description": clean_text(
                item.get("contents", "")
            )[:350],
            "date": int(item.get("date", 0)),
            "source": "Steam"
        })

    print("Steam:", len(articles), "annunci")
    return articles


def get_official():
    response = session.get(
        OFFICIAL_URL,
        timeout=25
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text, "html.parser"
    )

    articles = []
    known_urls = set()

    for link in soup.select('a[href]'):
        href = link.get("href", "")
        url = urljoin(OFFICIAL_URL, href)
        parsed = urlparse(url)

        if parsed.netloc not in (
            "www.warframe.com",
            "warframe.com"
        ):
            continue

        if not re.match(
            r"^/(?:[a-z]{2}/)?news/[^/]+/?$",
            parsed.path
        ):
            continue

        if url in known_urls:
            continue

        title = clean_text(link.get_text(" ", strip=True))

        if not title or title.lower() == "read more":
            continue

        # Cerca data e descrizione nel contenitore
        # dell'articolo, senza prendere l'intera pagina.
        container = link.parent
        date_match = None
        context = ""

        for _ in range(4):
            if container is None:
                break

            context = clean_text(
                container.get_text(" ", strip=True)
            )

            date_match = re.search(
                r"Posted On\s+"
                r"(\d{4}-\d{2}-\d{2})"
                r"\s+(\d{2}:\d{2}:\d{2})",
                context,
                re.IGNORECASE
            )

            if date_match:
                break

            container = container.parent

        if not date_match:
            continue

        date_string = (
            date_match.group(1) + " " +
            date_match.group(2)
        )

        timestamp = int(
            datetime.strptime(
                date_string, "%Y-%m-%d %H:%M:%S"
            ).replace(
                tzinfo=timezone.utc
            ).timestamp()
        )

        description = context.replace(title, "", 1)
        description = re.sub(
            r"Posted On\s+\d{4}-\d{2}-\d{2}"
            r"\s+\d{2}:\d{2}:\d{2}",
            "",
            description,
            flags=re.IGNORECASE
        )
        description = description.replace(
            "Read More", ""
        ).strip()

        articles.append({
            "id": article_id(title),
            "title": title,
            "url": url,
            "description": description[:350],
            "date": timestamp,
            "source": "Warframe.com"
        })

        known_urls.add(url)

    print(
        "Warframe.com:",
        len(articles),
        "articoli"
    )
    return articles


def get_articles():
    articles = []
    successful_sources = 0

    for name, getter in [
        ("Steam", get_steam),
        ("Warframe.com", get_official)
    ]:
        try:
            result = getter()
            if not result:
                print(
                    "ATTENZIONE:",
                    name,
                    "non ha restituito articoli."
                )
                continue

            articles.extend(result)
            successful_sources += 1

        except Exception as error:
            print(
                "ERRORE fonte",
                name,
                str(error)
            )

    if successful_sources == 0:
        raise RuntimeError(
            "Nessuna fonte ha restituito notizie."
        )

    # Priorita' agli articoli del sito ufficiale.
    articles.sort(
        key=lambda a: a["source"] == "Warframe.com"
    )

    unique = {}

    for article in articles:
        unique[article["id"]] = article

    result = sorted(
        unique.values(),
        key=lambda a: a["date"]
    )

    print("Articoli unici:", len(result))
    return result


def send_discord(article):
    if not WEBHOOK:
        raise RuntimeError(
            "Webhook Discord Warframe mancante."
        )

    embed = {
        "title": article["title"][:256],
        "description": article["description"][:350],
        "url": article["url"],
        "color": 0x65B32E,
        "footer": {
            "text": (
                "ARTYKO NEWS NETWORK | WARFRAME"
                " | " + article["source"]
            )
        },
        "timestamp": datetime.fromtimestamp(
            article["date"],
            tz=timezone.utc
        ).isoformat()
    }

    response = session.post(
        WEBHOOK,
        json={
            "username": "ARTYKO WARFRAME NEWS",
            "allowed_mentions": {"parse": []},
            "embeds": [embed]
        },
        timeout=30
    )
    response.raise_for_status()

    print("Pubblicata:", article["title"])


def main():
    print("=" * 48)
    print("ARTYKO | WARFRAME NEWS")
    print("Simulazione:", DRY_RUN)
    print("=" * 48)

    articles = get_articles()

    if STATE.exists():
        seen = set(json.loads(
            STATE.read_text(encoding="utf-8")
        ))
        selected = [
            a for a in articles
            if a["id"] not in seen
        ]
    else:
        seen = set()
        selected = articles[-FIRST_RUN_LIMIT:]

    print("Notizie selezionate:", len(selected))

    for article in selected:
        print(
            article["source"],
            "|",
            article["title"],
            "|",
            article["url"]
        )

        if not DRY_RUN:
            send_discord(article)
            time.sleep(2)

            # Salvataggio progressivo:
            # evita duplicati dopo errori parziali.
            seen.add(article["id"])
            STATE.write_text(
                json.dumps(sorted(seen), indent=2),
                encoding="utf-8"
            )

    if DRY_RUN:
        print(
            "TEST COMPLETATO: "
            "nessun messaggio pubblicato."
        )
        return

    # Segna come gia' viste anche le notizie
    # precedenti al primo avvio.
    seen.update(a["id"] for a in articles)

    STATE.write_text(
        json.dumps(sorted(seen), indent=2),
        encoding="utf-8"
    )

    print("Storico aggiornato.")


if __name__ == "__main__":
    main()
