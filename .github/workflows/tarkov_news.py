
import os
import re
import json
import time
import html
import requests

from pathlib import Path
from datetime import datetime, timezone

APP_ID = 3932890
API_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

STATE = Path("tarkov_seen_articles.json")

WEBHOOK = os.getenv("DISCORD_WEBHOOK_TARKOV", "")
DRY_RUN = os.getenv("TARKOV_DRY_RUN", "true").lower() != "false"

MAX_NEWS = 100
FIRST_RUN_LIMIT = 3

session = requests.Session()
session.headers.update({
    "User-Agent": "ARTYKO-News-Bot/1.0"
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
        raise RuntimeError("Webhook Tarkov mancante")

    embed = {
        "title": article["title"][:256],
        "description": article["description"][:350],
        "color": 0x00D9D0,
        "footer": {
            "text": "ARTYKO NEWS NETWORK | ESCAPE FROM TARKOV"
        },
        "timestamp": datetime.fromtimestamp(
            article["date"],
            tz=timezone.utc
        ).isoformat()
    }

    if article["url"].startswith("https://"):
        embed["url"] = article["url"]

    response = session.post(
        WEBHOOK,
        json={"embeds": [embed]},
        timeout=20
    )

    response.raise_for_status()


def main():
    articles = get_articles()

    if not articles:
        raise RuntimeError(
            "Nessun annuncio trovato. Storico non modificato."
        )

    first_run = not STATE.exists()

    if first_run:
        seen = set()
        selected = articles[-FIRST_RUN_LIMIT:]
    else:
        seen = set(json.loads(
            STATE.read_text(encoding="utf-8")
        ))

        selected = [
            article for article in articles
            if article["id"] not in seen
        ]

    print("NOTIZIE DA PUBBLICARE:", len(selected), flush=True)

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

    print("Storico Tarkov aggiornato.", flush=True)


if __name__ == "__main__":
    main()
