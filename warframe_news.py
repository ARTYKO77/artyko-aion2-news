
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


# ============================================================
# ARTYKO | WARFRAME NEWS
#
# Fonti:
# - Steam News
# - Warframe.com
#
# Funzioni:
# - Controllo notizie
# - Protezione duplicati
# - Copertine ufficiali
# - Copertina ARTYKO alternativa
# - Simulazione sicura
# - Storico pubblicazioni
# ============================================================


APP_ID = 230410

STEAM_API = (
    "https://api.steampowered.com/"
    "ISteamNews/GetNewsForApp/v2/"
)

OFFICIAL_URL = "https://www.warframe.com/en/news"

BASE_DIR = Path(__file__).resolve().parent

STATE = BASE_DIR / "warframe_seen_articles.json"
COVER = BASE_DIR / "warframe_cover.png"

WEBHOOK = os.getenv(
    "DISCORD_WEBHOOK_WARFRAME", ""
).strip()

DRY_RUN = (
    os.getenv("WARFRAME_DRY_RUN", "true")
    .strip()
    .lower() != "false"
)

MAX_NEWS = 100
FIRST_RUN_LIMIT = 3
MAX_IMAGE_BYTES = 8 * 1024 * 1024

session = requests.Session()

session.headers.update({
    "User-Agent": "ARTYKO-Warframe-News/1.0"
})


# ============================================================
# PULIZIA TESTI E IDENTIFICAZIONE NOTIZIE
# ============================================================

def clean_text(value):
    value = re.sub(
        r"\[/?[^\]]+\]",
        " ",
        str(value)
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value
    )

    return " ".join(
        html.unescape(value).split()
    )


def title_key(title):
    title = unicodedata.normalize(
        "NFKD",
        title
    )

    title = "".join(
        char
        for char in title
        if not unicodedata.combining(char)
    )

    return re.sub(
        r"[^a-z0-9]",
        "",
        title.lower()
    )


def article_id(title):
    return hashlib.sha256(
        title_key(title).encode("utf-8")
    ).hexdigest()


# ============================================================
# RECUPERO NOTIZIE STEAM
# ============================================================

def get_steam():
    response = session.get(
        STEAM_API,
        params={
            "appid": APP_ID,
            "count": MAX_NEWS,
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

        title = clean_text(
            item.get("title", "")
        )

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
            "date": int(
                item.get("date", 0)
            ),
            "source": "Steam"
        })

    print(
        "Steam:",
        len(articles),
        "annunci",
        flush=True
    )

    return articles


# ============================================================
# RECUPERO NOTIZIE WARFRAME.COM
# ============================================================

def get_official():
    response = session.get(
        OFFICIAL_URL,
        timeout=25
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    articles = []
    known_urls = set()

    for link in soup.select("a[href]"):
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

        title = clean_text(
            link.get_text(" ", strip=True)
        )

        if not title:
            continue

        if title.lower() == "read more":
            continue

        container = link.parent
        date_match = None
        context = ""

        for _ in range(4):
            if container is None:
                break

            context = clean_text(
                container.get_text(
                    " ",
                    strip=True
                )
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
            date_match.group(1)
            + " "
            + date_match.group(2)
        )

        timestamp = int(
            datetime.strptime(
                date_string,
                "%Y-%m-%d %H:%M:%S"
            ).replace(
                tzinfo=timezone.utc
            ).timestamp()
        )

        description = context.replace(
            title,
            "",
            1
        )

        description = re.sub(
            r"Posted On\s+"
            r"\d{4}-\d{2}-\d{2}"
            r"\s+\d{2}:\d{2}:\d{2}",
            "",
            description,
            flags=re.IGNORECASE
        )

        description = description.replace(
            "Read More",
            ""
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
        "articoli",
        flush=True
    )

    return articles


# ============================================================
# UNIONE FONTI E CONTROLLO DUPLICATI
# ============================================================

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
                    "non ha restituito articoli.",
                    flush=True
                )
                continue

            articles.extend(result)
            successful_sources += 1

        except Exception as error:
            print(
                "ERRORE fonte:",
                name,
                str(error),
                flush=True
            )

    if successful_sources == 0:
        raise RuntimeError(
            "Nessuna fonte ha restituito notizie."
        )

    # Gli articoli del sito ufficiale
    # hanno priorita' sui duplicati Steam.

    articles.sort(
        key=lambda article: (
            article["source"] == "Warframe.com"
        )
    )

    unique = {}

    for article in articles:
        unique[article["id"]] = article

    result = sorted(
        unique.values(),
        key=lambda article: article["date"]
    )

    print(
        "Articoli unici:",
        len(result),
        flush=True
    )

    return result


# ============================================================
# RECUPERO COPERTINA UFFICIALE
# ============================================================

def find_official_image(article):
    url = article["url"]

    parsed = urlparse(url)

    # Per sicurezza cerchiamo immagini soltanto
    # nelle pagine ufficiali di Warframe.

    if parsed.hostname not in (
        "www.warframe.com",
        "warframe.com"
    ):
        return None

    try:
        response = session.get(
            url,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        meta = soup.find(
            "meta",
            property="og:image"
        )

        if not meta:
            meta = soup.find(
                "meta",
                attrs={"name": "twitter:image"}
            )

        if not meta:
            return None

        image_url = urljoin(
            url,
            meta.get("content", "")
        )

        if image_url.startswith("https://"):
            return image_url

    except requests.RequestException as error:
        print(
            "Copertina ufficiale non disponibile:",
            error,
            flush=True
        )

    return None


# ============================================================
# COPERTINA UFFICIALE O ARTYKO
# ============================================================

def get_cover(article):
    image_url = find_official_image(article)

    if image_url:
        try:
            response = session.get(
                image_url,
                timeout=25,
                stream=True
            )

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type",
                ""
            ).split(";")[0].lower()

            extensions = {
                "image/png": "png",
                "image/jpeg": "jpg",
                "image/webp": "webp"
            }

            if content_type not in extensions:
                raise ValueError(
                    "Formato immagine non supportato."
                )

            image_data = bytearray()

            for chunk in response.iter_content(
                65536
            ):
                image_data.extend(chunk)

                if len(image_data) > MAX_IMAGE_BYTES:
                    raise ValueError(
                        "Immagine troppo grande."
                    )

            if not image_data:
                raise ValueError(
                    "Immagine vuota."
                )

            filename = (
                "warframe_official."
                + extensions[content_type]
            )

            print(
                "Copertina ufficiale trovata.",
                flush=True
            )

            return (
                filename,
                bytes(image_data),
                content_type
            )

        except (
            requests.RequestException,
            ValueError
        ) as error:
            print(
                "Copertina ufficiale non utilizzabile:",
                error,
                flush=True
            )

    if not COVER.is_file():
        raise FileNotFoundError(
            "Copertina ARTYKO mancante: "
            "warframe_cover.png"
        )

    print(
        "Utilizzo copertina ARTYKO.",
        flush=True
    )

    return (
        "warframe_cover.png",
        COVER.read_bytes(),
        "image/png"
    )


# ============================================================
# PUBBLICAZIONE SU DISCORD
# ============================================================

def send_discord(article):
    if not WEBHOOK:
        raise RuntimeError(
            "Webhook Discord Warframe mancante."
        )

    filename, image_data, content_type = get_cover(
        article
    )

    embed = {
        "title": article["title"][:256],
        "description": article["description"][:350],
        "url": article["url"],
        "color": 0x00D9D0,
        "image": {
            "url": "attachment://" + filename
        },
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

    payload = {
        "username": "ARTYKO WARFRAME NEWS",
        "allowed_mentions": {
            "parse": []
        },
        "embeds": [embed]
    }

    response = session.post(
        WEBHOOK,
        data={
            "payload_json": json.dumps(
                payload
            )
        },
        files={
            "files[0]": (
                filename,
                image_data,
                content_type
            )
        },
        timeout=30
    )

    response.raise_for_status()

    print(
        "Notizia pubblicata:",
        article["title"],
        flush=True
    )


# ============================================================
# STORICO NOTIZIE
# ============================================================

def load_seen():
    if not STATE.exists():
        return set()

    data = json.loads(
        STATE.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(data, list):
        raise ValueError(
            "Formato storico non valido."
        )

    return set(data)


def save_seen(seen):
    STATE.write_text(
        json.dumps(
            sorted(seen),
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# ESECUZIONE PRINCIPALE
# ============================================================

def main():
    print("=" * 48)
    print("ARTYKO | WARFRAME NEWS")
    print("=" * 48)

    print(
        "Modalita' simulazione:",
        DRY_RUN,
        flush=True
    )

    print(
        "Webhook configurato:",
        bool(WEBHOOK),
        flush=True
    )

    print(
        "Copertina ARTYKO presente:",
        COVER.is_file(),
        flush=True
    )

    articles = get_articles()

    if not articles:
        raise RuntimeError(
            "Nessun articolo trovato."
        )

    first_run = not STATE.exists()
    seen = load_seen()

    if first_run:
        selected = articles[
            -FIRST_RUN_LIMIT:
        ]
    else:
        selected = [
            article
            for article in articles
            if article["id"] not in seen
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
            "|",
            article["title"],
            "|",
            article["url"],
            flush=True
        )

        if not DRY_RUN:
            send_discord(article)

            seen.add(article["id"])
            save_seen(seen)

            time.sleep(2)

    if DRY_RUN:
        print(
            "SIMULAZIONE COMPLETATA. "
            "Nessun messaggio inviato. "
            "Storico invariato.",
            flush=True
        )
        return

    # Al primo avvio registriamo anche
    # le notizie precedenti per evitare
    # di pubblicarle nei controlli futuri.

    seen.update(
        article["id"]
        for article in articles
    )

    save_seen(seen)

    print(
        "Storico Warframe aggiornato.",
        flush=True
    )


if __name__ == "__main__":
    main()
