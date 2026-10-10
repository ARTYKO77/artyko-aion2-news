
import os
import json
import re
import html
import time
import requests

from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

BLOG = "https://www.callofduty.com/blog"
STATE = Path("cod_seen_articles.json")
WEBHOOK = os.getenv("DISCORD_WEBHOOK_COD", "")
DRY_RUN = os.getenv("COD_DRY_RUN", "true").lower() == "true"

HEADERS = {"User-Agent": "Mozilla/5.0"}
PATTERN = re.compile(r"^/blog/20\d{2}/\d{2}/")


def get_jsonld(article_url):
    response = requests.get(
        article_url, headers=HEADERS, timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for script in soup.find_all(
        "script", type="application/ld+json"
    ):
        try:
            data = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]

        for item in candidates:
            if not isinstance(item, dict):
                continue

            if item.get("@type") in (
                "BlogPosting", "NewsArticle", "Article"
            ):
                return item

    return {}


def get_articles():
    response = requests.get(
        BLOG, headers=HEADERS, timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    links = set()

    for a in soup.find_all("a", href=True):
        url = urljoin(BLOG, a["href"])
        parsed = urlparse(url)

        if parsed.netloc not in (
            "www.callofduty.com", "callofduty.com"
        ):
            continue

        if PATTERN.match(parsed.path):
            clean_url = parsed._replace(
                query="", fragment=""
            ).geturl()
            links.add(clean_url)

    print("Link articoli trovati:", len(links))

    articles = []

    for index, url in enumerate(sorted(links), 1):
        try:
            data = get_jsonld(url)

            title = html.unescape(
                data.get("headline", "")
            ).strip()
            published = data.get("datePublished", "")

            if not title or not published:
                continue

            image = data.get("image", "")
            if isinstance(image, list):
                image = image[0] if image else ""
            if isinstance(image, dict):
                image = image.get("url", "")

            date = datetime.fromisoformat(
                published.replace("Z", "+00:00")
            )

            articles.append({
                "url": url,
                "title": title,
                "date": date,
                "image": image,
                "description": html.unescape(
                    data.get("description", "")
                ).strip()
            })

        except Exception as error:
            print("Errore articolo:", url, error)

        if index % 25 == 0:
            print(f"Analizzati {index}/{len(links)} link")

    articles.sort(
        key=lambda article: article["date"],
        reverse=True
    )

    return articles


def send_discord(article):
    if not WEBHOOK:
        raise RuntimeError("Webhook COD mancante")

    embed = {
        "title": article["title"][:256],
        "url": article["url"],
        "description": article["description"][:300],
        "color": 0x00D9D0,
        "footer": {
            "text": "ARTYKO NEWS NETWORK | CALL OF DUTY"
        }
    }

    if article["image"]:
        embed["image"] = {"url": article["image"]}

    response = requests.post(
        WEBHOOK,
        json={"embeds": [embed]},
        timeout=30
    )
    response.raise_for_status()


def main():
    articles = get_articles()
    print("Articoli validi:", len(articles))

    if not articles:
        raise RuntimeError("Nessun articolo valido")

    if STATE.exists():
        seen = set(json.loads(
            STATE.read_text(encoding="utf-8")
        ))
        selected = [
            a for a in articles if a["url"] not in seen
        ]
    else:
        seen = set()
        selected = articles[:3]

    print("Notizie da pubblicare:", len(selected))

    for article in reversed(selected):
        print(
            "NOTIZIA:",
            article["date"].isoformat(),
            article["title"],
            article["url"]
        )

        if not DRY_RUN:
            send_discord(article)
            time.sleep(2)

    if DRY_RUN:
        print("SIMULAZIONE: nessun messaggio inviato")
        return

    seen.update(a["url"] for a in articles)

    STATE.write_text(
        json.dumps(
            sorted(seen),
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("Storico COD aggiornato")


if __name__ == "__main__":
    main()
