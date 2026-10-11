
import os
import re
import json
import time
import html
import requests

from pathlib import Path
from datetime import datetime, timezone

# ARTYKO WARDOGS NEWS
APP_ID = 1867240
API_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

BASE_DIR = Path(__file__).resolve().parent
STATE = BASE_DIR / "wardogs_seen_articles.json"
COVER = BASE_DIR / "wardogs_cover.png"

WEBHOOK = os.getenv("DISCORD_WEBHOOK_WARDOGS", "")
DRY_RUN = os.getenv("WARDOGS_DRY_RUN", "true").lower() != "false"

MAX_NEWS = 100
FIRST_RUN_LIMIT = 3

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-WARDOGS-News-Bot/1.0"
})


def clean_text(value):
    value = re.sub(r"\[/?[^\]]+\]", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
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
    items = data.get("appnews", {}).get("newsitems", [])

    print("Notizie ricevute:", len(items), flush=True)

    articles = []

    for item in items:
        # Solo annunci della community Steam
        if item.get("feed_type") != 1:
            continue

        if item.get("feedlabel") != "Community Announcements":
            continue

        title = clean_text(item.get("title", ""))
        content = clean_text(item.get("contents", ""))

        if not title or not item.get("gid"):
            continue

        articles.append({
            "id": str(item["gid"]),
            "title": title,
            "url": item.get("url", ""),
            "description": content[:350],
            "date": int(item.get("date", 0))
        })

    articles.sort(key=lambda a: a["date"])

    print("Annunci selezionati:", len(articles), flush=True)

    return articles


def send_discord(article):
    if not WEBHOOK:
        raise RuntimeError("Webhook WARDOGS mancante")

    embed = {
        "title": article["title"][:256],
        "description": article["description"][:350],
        "color": 0x00D9D0,
        "footer": {
            "text": "ARTYKO NEWS NETWORK | WARDOGS"
        },
        "timestamp": datetime.fromtimestamp(
            article["date"],
            tz=timezone.utc
        ).isoformat()
    }

    if article["url"].startswith("https://"):
        embed["url"] = article["url"]

    if COVER.is_file():
        embed["image"] = {
            "url": "attachment://wardogs_cover.png"
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
                        "wardogs_cover.png",
                        image,
                        "image/png"
                    )
                },
                timeout=30
            )
    else:
        print(
            "ATTENZIONE: copertina non trovata!",
            flush=True
        )

        response = session.post(
            WEBHOOK,
            json={"embeds": [embed]},
            timeout=20
        )

    response.raise_for_status()


def main():
    articles = get_articles()

    if not articles:
        print(
            "Nessun annuncio trovato. "
            "Storico non modificato.",
            flush=True
        )
        return

    first_run = not STATE.exists()

    if first_run:
        selected = articles[-FIRST_RUN_LIMIT:]
        seen = set()
    else:
        seen = set(json.loads(
            STATE.read_text(encoding="utf-8")
        ))

        selected = [
            article for article in articles
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

    seen.update(article["id"] for article in articles)

    STATE.write_text(
        json.dumps(sorted(seen), indent=2),
        encoding="utf-8"
    )

    print(
        "Storico WARDOGS aggiornato.",
        flush=True
    )


if __name__ == "__main__":
    main()
