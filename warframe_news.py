
import os
import re
import json
import time
import html
import hashlib
import unicodedata
import requests

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup


# ============================================================
# ARTYKO | WARFRAME NEWS
# Steam + Warframe.com
# Copertine ufficiali + fallback ARTYKO
# Storico sicuro, inizializzazione e test separati
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
    .strip().lower() != "false"
)
TEST_COVER = (
    os.getenv("WARFRAME_TEST_COVER", "false")
    .strip().lower() == "true"
)
TEST_OFFICIAL = (
    os.getenv("WARFRAME_TEST_OFFICIAL", "false")
    .strip().lower() == "true"
)
INIT_HISTORY = (
    os.getenv("WARFRAME_INIT_HISTORY", "false")
    .strip().lower() == "true"
)

MAX_NEWS = 100
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-Warframe-News/1.0"
})


# ============================================================
# UTILITA'
# ============================================================

def clean_text(value):
    value = re.sub(r"\[/?[^\]]+\]", " ", str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def article_id(title):
    normalized = unicodedata.normalize("NFKD", title)
    normalized = "".join(
        c for c in normalized
        if not unicodedata.combining(c)
    )
    normalized = re.sub(
        r"[^a-z0-9]", "", normalized.lower()
    )
    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def load_seen():
    if not STATE.exists():
        return set()

    data = json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Formato storico non valido.")

    return set(str(item) for item in data)


def save_seen(seen):
    STATE.write_text(
        json.dumps(sorted(seen), indent=2),
        encoding="utf-8"
    )


# ============================================================
# STEAM
# ============================================================

def get_steam():
    response = session.get(
        STEAM_API,
        params={
            "appid": APP_ID,
            "count": MAX_NEWS,
            "maxlength": 0,
            "format": "json",
        },
        timeout=25,
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
        url = item.get("url", "")

        if not title or not url.startswith("https://"):
            continue

        articles.append({
            "id": article_id(title),
            "title": title,
            "url": url,
            "description": clean_text(
                item.get("contents", "")
            )[:350],
            "date": int(item.get("date", 0)),
            "source": "Steam",
        })

    print("Steam:", len(articles), "annunci", flush=True)
    return articles


# ============================================================
# SITO UFFICIALE WARFRAME
# ============================================================

def get_official():
    response = session.get(OFFICIAL_URL, timeout=25)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = []
    known_urls = set()

    for link in soup.select("a[href]"):
        url = urljoin(OFFICIAL_URL, link.get("href", ""))
        parsed = urlparse(url)

        if parsed.netloc not in (
            "www.warframe.com", "warframe.com"
        ):
            continue

        if not re.match(
            r"^/(?:[a-z]{2}/)?news/[^/]+/?$",
            parsed.path,
        ):
            continue

        if url in known_urls:
            continue

        title = clean_text(link.get_text(" ", strip=True))
        if not title or title.lower() == "read more":
            continue

        container = link.parent
        date_match = None
        context = ""

        for _ in range(5):
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
                re.IGNORECASE,
            )

            if date_match:
                break

            container = container.parent

        if not date_match:
            continue

        try:
            timestamp = int(
                datetime.strptime(
                    date_match.group(1) + " " +
                    date_match.group(2),
                    "%Y-%m-%d %H:%M:%S",
                ).replace(tzinfo=timezone.utc).timestamp()
            )
        except ValueError:
            continue

        description = context.replace(title, "", 1)
        description = re.sub(
            r"Posted On\s+\d{4}-\d{2}-\d{2}"
            r"\s+\d{2}:\d{2}:\d{2}",
            "",
            description,
            flags=re.IGNORECASE,
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
            "source": "Warframe.com",
        })
        known_urls.add(url)

    print(
        "Warframe.com:", len(articles), "articoli",
        flush=True
    )
    return articles


# ============================================================
# UNIONE DELLE FONTI
# ============================================================

def get_articles():
    collected = []
    successful_sources = 0

    for name, getter in (
        ("Steam", get_steam),
        ("Warframe.com", get_official),
    ):
        try:
            result = getter()
            successful_sources += 1
            collected.extend(result)
        except Exception as error:
            print(
                "ERRORE fonte", name, ":", error,
                flush=True
            )

    if successful_sources == 0:
        raise RuntimeError(
            "Entrambe le fonti hanno fallito."
        )

    # Se il titolo e' presente su entrambe le fonti,
    # preferisci il link ufficiale Warframe.com.
    unique = {}

    for article in collected:
        key = article["id"]
        existing = unique.get(key)

        if (
            existing is None
            or article["source"] == "Warframe.com"
        ):
            unique[key] = article

    articles = sorted(
        unique.values(),
        key=lambda item: item["date"]
    )

    print(
        "Articoli unici:", len(articles),
        flush=True
    )

    return articles


# ============================================================
# COPERTINE UFFICIALI E FALLBACK ARTYKO
# ============================================================

def find_official_image(article):
    parsed = urlparse(article["url"])

    if parsed.hostname not in (
        "www.warframe.com", "warframe.com"
    ):
        return None

    try:
        response = session.get(
            article["url"], timeout=20
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        meta = soup.find("meta", property="og:image")

        if not meta:
            meta = soup.find(
                "meta",
                attrs={"name": "twitter:image"}
            )

        if not meta or not meta.get("content"):
            return None

        image_url = urljoin(
            article["url"], meta["content"]
        )

        if urlparse(image_url).scheme == "https":
            return image_url

    except requests.RequestException as error:
        print(
            "Recupero immagine ufficiale fallito:",
            error,
            flush=True
        )

    return None


def get_cover(article):
    image_url = find_official_image(article)

    if image_url:
        try:
            response = session.get(
                image_url,
                timeout=25,
                stream=True,
            )
            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            ).split(";")[0].lower()

            if content_type not in IMAGE_TYPES:
                raise ValueError(
                    "Formato immagine non supportato."
                )

            image_data = bytearray()

            for chunk in response.iter_content(65536):
                image_data.extend(chunk)

                if len(image_data) > MAX_IMAGE_BYTES:
                    raise ValueError(
                        "Immagine superiore a 8 MB."
                    )

            if image_data:
                extension = IMAGE_TYPES[content_type]
                print(
                    "Copertina ufficiale trovata.",
                    flush=True
                )
                return (
                    f"warframe_official.{extension}",
                    bytes(image_data),
                    content_type,
                )

        except (
            requests.RequestException, ValueError
        ) as error:
            print(
                "Immagine ufficiale non utilizzabile:",
                error,
                flush=True
            )

    if not COVER.is_file():
        raise FileNotFoundError(
            "Manca warframe_cover.png."
        )

    print("Utilizzo copertina ARTYKO.", flush=True)

    return (
        "warframe_cover.png",
        COVER.read_bytes(),
        "image/png",
    )


# ============================================================
# INVIO DISCORD
# ============================================================

def post_embed(embed, cover):
    if not WEBHOOK:
        raise RuntimeError(
            "Secret DISCORD_WEBHOOK_WARFRAME mancante."
        )

    filename, image_data, content_type = cover

    embed["image"] = {
        "url": "attachment://" + filename
    }

    payload = {
        "username": "ARTYKO WARFRAME NEWS",
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }

    response = session.post(
        WEBHOOK,
        data={"payload_json": json.dumps(payload)},
        files={
            "files[0]": (
                filename, image_data, content_type
            )
        },
        timeout=30,
    )
    response.raise_for_status()

    print("Messaggio Discord inviato.", flush=True)


def send_discord(article):
    cover = get_cover(article)

    embed = {
        "title": article["title"][:256],
        "description": article["description"][:350],
        "url": article["url"],
        "color": 0x00D9D0,
        "footer": {
            "text": (
                "ARTYKO NEWS NETWORK | WARFRAME | "
                + article["source"]
            )
        },
        "timestamp": datetime.fromtimestamp(
            article["date"], tz=timezone.utc
        ).isoformat(),
    }

    post_embed(embed, cover)

    print(
        "Notizia pubblicata:", article["title"],
        flush=True
    )


# ============================================================
# TEST COPERTINA
# ============================================================

def send_cover_test():
    if not COVER.is_file():
        raise FileNotFoundError(
            "Manca warframe_cover.png."
        )

    if DRY_RUN:
        print(
            "SIMULAZIONE: test copertina non inviato.",
            flush=True
        )
        return

    embed = {
        "title": "TEST COPERTINA | ARTYKO WARFRAME NEWS",
        "description": (
            "Verifica della copertina personalizzata ARTYKO. "
            "Questo messaggio e' soltanto un test."
        ),
        "color": 0x00D9D0,
        "footer": {
            "text": "ARTYKO NEWS NETWORK | TEST"
        },
    }

    post_embed(embed, (
        "warframe_cover.png",
        COVER.read_bytes(),
        "image/png",
    ))

    print("TEST COPERTINA COMPLETATO.", flush=True)


# ============================================================
# TEST SINGOLA NOTIZIA UFFICIALE
# ============================================================

def send_official_news_test():
    articles = get_official()

    if not articles:
        raise RuntimeError(
            "Nessuna notizia ufficiale trovata."
        )

    article = max(
        articles, key=lambda item: item["date"]
    )

    print(
        "Articolo di test:",
        article["title"],
        article["url"],
        flush=True
    )

    if DRY_RUN:
        print(
            "SIMULAZIONE: notizia non inviata.",
            flush=True
        )
        return

    send_discord(article)
    print(
        "Test ufficiale completato. Storico invariato.",
        flush=True
    )


# ============================================================
# INIZIALIZZAZIONE SICURA DELLO STORICO
# ============================================================

def initialize_history(articles):
    if not articles:
        raise RuntimeError(
            "Nessun articolo recuperato: storico non creato."
        )

    seen = {article["id"] for article in articles}
    save_seen(seen)

    print(
        "INIZIALIZZAZIONE COMPLETATA.",
        flush=True
    )
    print(
        "Articoli registrati:",
        len(seen),
        flush=True
    )
    print(
        "Nessun messaggio Discord inviato.",
        flush=True
    )


# ============================================================
# PROGRAMMA PRINCIPALE
# ============================================================

def main():
    print("=" * 48)
    print("ARTYKO | WARFRAME NEWS")
    print("=" * 48)
    print("Simulazione:", DRY_RUN, flush=True)
    print("Test copertina:", TEST_COVER, flush=True)
    print("Test notizia ufficiale:", TEST_OFFICIAL, flush=True)
    print("Inizializza storico:", INIT_HISTORY, flush=True)
    print("Webhook configurato:", bool(WEBHOOK), flush=True)
    print("Copertina presente:", COVER.is_file(), flush=True)

    if sum((TEST_COVER, TEST_OFFICIAL, INIT_HISTORY)) > 1:
        raise RuntimeError(
            "Seleziona una sola modalita' speciale per esecuzione."
        )

    # Le modalita' di test non toccano lo storico.
    if TEST_COVER:
        send_cover_test()
        return

    if TEST_OFFICIAL:
        send_official_news_test()
        return

    articles = get_articles()

    if not articles:
        raise RuntimeError(
            "Nessun articolo trovato."
        )

    # Inizializzazione richiesta manualmente:
    # registra lo stato corrente senza pubblicare.
    if INIT_HISTORY:
        initialize_history(articles)
        return

    # Sicurezza: al primo avvio effettivo, crea lo storico
    # e termina senza pubblicare notizie arretrate.
    if not STATE.exists():
        if DRY_RUN:
            print(
                "ATTENZIONE: storico assente. "
                "Simulazione senza inizializzazione.",
                flush=True
            )
            print(
                "Notizie disponibili:",
                len(articles),
                flush=True
            )
            return

        initialize_history(articles)
        return

    seen = load_seen()

    selected = [
        article for article in articles
        if article["id"] not in seen
    ]

    print(
        "NOTIZIE NUOVE:", len(selected),
        flush=True
    )

    if DRY_RUN:
        for article in selected:
            print(
                "SIMULAZIONE:",
                article["source"],
                "|",
                article["title"],
                "|",
                article["url"],
                flush=True
            )

        print(
            "SIMULAZIONE COMPLETATA. "
            "Nessun messaggio inviato; storico invariato.",
            flush=True
        )
        return

    for article in selected:
        send_discord(article)
        seen.add(article["id"])
        save_seen(seen)
        time.sleep(2)

    # Registra anche gli articoli già presenti che non sono
    # nuovi, così lo storico resta sincronizzato con le fonti.
    seen.update(article["id"] for article in articles)
    save_seen(seen)

    print(
        "Storico Warframe aggiornato.",
        flush=True
    )


if __name__ == "__main__":
    main()
