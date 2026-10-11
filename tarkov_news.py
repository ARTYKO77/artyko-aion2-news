
import os
import re
import json
import time
import html
import requests

from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# ARTYKO | ESCAPE FROM TARKOV NEWS
# Notizie Steam + copertina personalizzata
# Modalita' test copertina senza modificare lo storico
# ============================================================

APP_ID = 3932890
API_URL = (
    "https://api.steampowered.com/"
    "ISteamNews/GetNewsForApp/v2/"
)

BASE_DIR = Path(__file__).resolve().parent

STATE = BASE_DIR / "tarkov_seen_articles.json"
COVER = BASE_DIR / "tarkov_cover.png"

WEBHOOK = os.getenv(
    "DISCORD_WEBHOOK_TARKOV", ""
).strip()

DRY_RUN = (
    os.getenv("TARKOV_DRY_RUN", "true")
    .strip()
    .lower() != "false"
)

TEST_COVER = (
    os.getenv("TARKOV_TEST_COVER", "false")
    .strip()
    .lower() == "true"
)

MAX_NEWS = 100
FIRST_RUN_LIMIT = 3

session = requests.Session()

session.headers.update({
    "User-Agent": "ARTYKO-News-Bot/1.0"
})


def clean_text(value):
    value = re.sub(
        r"\[/?[^\]]+\]",
        " ",
        value
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value
    )

    value = html.unescape(value)

    return " ".join(value.split())


def get_articles():
    response = session.get(
        API_URL,
        params={
            "appid": APP_ID,
            "count": MAX_NEWS,
            "maxlength": 0,
            "format": "json"
        },
        timeout=25
    )

    response.raise_for_status()

    data = response.json()

    items = data.get(
        "appnews", {}
    ).get("newsitems", [])

    print(
        "Notizie ricevute:",
        len(items),
        flush=True
    )

    articles = []

    for item in items:
        if item.get("feed_type") != 1:
            continue

        if (
            item.get("feedlabel")
            != "Community Announcements"
        ):
            continue

        title = clean_text(
            item.get("title", "")
        )

        content = clean_text(
            item.get("contents", "")
        )

        if not title or not item.get("gid"):
            continue

        articles.append({
            "id": str(item["gid"]),
            "title": title,
            "url": item.get("url", ""),
            "description": content[:350],
            "date": int(
                item.get("date", 0)
            )
        })

    articles.sort(
        key=lambda article: article["date"]
    )

    print(
        "Annunci selezionati:",
        len(articles),
        flush=True
    )

    return articles


def post_embed(embed):
    if not WEBHOOK:
        raise RuntimeError(
            "Webhook Tarkov mancante."
        )

    if not COVER.is_file():
        print(
            "ATTENZIONE: copertina non trovata!",
            flush=True
        )

        raise FileNotFoundError(
            f"Copertina mancante: {COVER}"
        )

    print(
        "Copertina trovata:",
        COVER.name,
        flush=True
    )

    print(
        "Dimensione copertina:",
        COVER.stat().st_size,
        "bytes",
        flush=True
    )

    embed["image"] = {
        "url": "attachment://tarkov_cover.png"
    }

    payload = {
        "allowed_mentions": {
            "parse": []
        },
        "embeds": [embed]
    }

    with COVER.open("rb") as image:
        response = session.post(
            WEBHOOK,
            data={
                "payload_json": json.dumps(
                    payload
                )
            },
            files={
                "files[0]": (
                    "tarkov_cover.png",
                    image,
                    "image/png"
                )
            },
            timeout=30
        )

    if response.status_code >= 400:
        raise RuntimeError(
            "Errore Discord HTTP "
            f"{response.status_code}: "
            f"{response.text[:500]}"
        )

    print(
        "Messaggio Discord inviato.",
        flush=True
    )


def send_discord(article):
    embed = {
        "title": article["title"][:256],
        "description": article[
            "description"
        ][:350],
        "color": 0x00D9D0,
        "footer": {
            "text": (
                "ARTYKO NEWS NETWORK | "
                "ESCAPE FROM TARKOV"
            )
        },
        "timestamp": datetime.fromtimestamp(
            article["date"],
            tz=timezone.utc
        ).isoformat()
    }

    if article["url"].startswith(
        "https://"
    ):
        embed["url"] = article["url"]

    post_embed(embed)


def send_cover_test():
    print(
        "\nMODALITA' TEST COPERTINA ATTIVA",
        flush=True
    )

    print(
        "Nessuna notizia reale verra' pubblicata.",
        flush=True
    )

    print(
        "Lo storico non verra' modificato.",
        flush=True
    )

    if not COVER.is_file():
        raise FileNotFoundError(
            f"Copertina non trovata: {COVER}"
        )

    print(
        "Copertina verificata:",
        COVER.name,
        flush=True
    )

    if DRY_RUN:
        print(
            "SIMULAZIONE: nessun messaggio inviato.",
            flush=True
        )
        return

    embed = {
        "title": "TEST COPERTINA | TARKOV NEWS",
        "description": (
            "Verifica dell'immagine personalizzata "
            "ARTYKO per le notizie di "
            "Escape from Tarkov.\n\n"
            "Questo messaggio e' soltanto un test "
            "e puo' essere eliminato."
        ),
        "color": 0x00D9D0,
        "footer": {
            "text": (
                "ARTYKO NEWS NETWORK | TEST"
            )
        }
    }

    post_embed(embed)

    print(
        "TEST COPERTINA COMPLETATO.",
        flush=True
    )


def main():
    print("=" * 48)
    print("ARTYKO | TARKOV NEWS")
    print("=" * 48)

    print(
        "Modalita' sicura:",
        DRY_RUN,
        flush=True
    )

    print(
        "Test copertina:",
        TEST_COVER,
        flush=True
    )

    print(
        "Webhook configurato:",
        bool(WEBHOOK),
        flush=True
    )

    # La modalita' test ha precedenza assoluta.
    # Non legge ne' modifica lo storico.
    # Non recupera e non pubblica notizie reali.

    if TEST_COVER:
        send_cover_test()
        return

    articles = get_articles()

    if not articles:
        raise RuntimeError(
            "Nessun annuncio trovato. "
            "Storico non modificato."
        )

    first_run = not STATE.exists()

    if first_run:
        seen = set()

        selected = articles[
            -FIRST_RUN_LIMIT:
        ]

    else:
        seen = set(
            json.loads(
                STATE.read_text(
                    encoding="utf-8"
                )
            )
        )

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
            article["title"],
            article["url"],
            flush=True
        )

        if not DRY_RUN:
            send_discord(article)
            time.sleep(2)

    if DRY_RUN:
        print(
            "SIMULAZIONE: nessun messaggio inviato.",
            flush=True
        )
        return

    seen.update(
        article["id"]
        for article in articles
    )

    STATE.write_text(
        json.dumps(
            sorted(seen),
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "Storico Tarkov aggiornato.",
        flush=True
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"ERRORE: {error}",
            flush=True
        )
        raise
