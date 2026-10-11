
import os
import re
import json
import html
import time
import requests

from io import BytesIO
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from PIL import Image

BLOG = "https://www.callofduty.com/blog"
STATE = Path("cod_seen_articles.json")

WEBHOOK = os.getenv("DISCORD_WEBHOOK_COD", "")
DRY_RUN = os.getenv("COD_DRY_RUN", "true").lower() != "false"

HEADERS = {"User-Agent": "Mozilla/5.0"}
PATTERN = re.compile(r"^/blog/20\d{2}/\d{2}/")
MAX_ARTICLES = 30

session = requests.Session()
session.headers.update(HEADERS)


def get_jsonld(url):
    response = session.get(url, timeout=(5, 10))
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for script in soup.find_all(
        "script", type="application/ld+json"
    ):
        try:
            data = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue

        items = data if isinstance(data, list) else [data]

        for item in items:
            if not isinstance(item, dict):
                continue

            if item.get("@type") in (
                "BlogPosting", "NewsArticle", "Article"
            ):
                return item

    return {}


def get_articles():
    response = session.get(BLOG, timeout=(5, 15))
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    links = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        url = urljoin(BLOG, a["href"])
        parsed = urlparse(url)

        if parsed.netloc not in (
            "www.callofduty.com", "callofduty.com"
        ):
            continue

        if not PATTERN.match(parsed.path):
            continue

        clean_url = parsed._replace(
            query="", fragment=""
        ).geturl()

        if clean_url not in seen_links:
            seen_links.add(clean_url)
            links.append(clean_url)

    print("Link totali:", len(links), flush=True)

    links = links[:MAX_ARTICLES]

    articles = []
    errors = 0

    for index, url in enumerate(links, 1):
        try:
            data = get_jsonld(url)

            title = html.unescape(
                data.get("headline", "")
            ).strip()

            published = data.get("datePublished", "")

            if not title or not published:
                errors += 1
                continue

            date = datetime.fromisoformat(
                published.replace("Z", "+00:00")
            )

            image = data.get("image", "")

            if isinstance(image, list):
                image = image[0] if image else ""

            if isinstance(image, dict):
                image = image.get("url", "")

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
            errors += 1
            print("Errore:", url, error, flush=True)

        print(
            f"Analizzati {index}/{len(links)}",
            flush=True
        )

    articles.sort(
        key=lambda a: a["date"],
        reverse=True
    )

    print("Articoli validi:", len(articles), flush=True)
    print("Articoli non letti:", errors, flush=True)

    return articles, errors


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

    image_url = article.get("image")

    if image_url:
        try:
            image_response = session.get(
                image_url,
                timeout=(5, 15)
            )
            image_response.raise_for_status()

            image_bytes = image_response.content

            if len(image_bytes) > 8 * 1024 * 1024:
                raise ValueError("Immagine troppo grande")

            picture = Image.open(BytesIO(image_bytes))
            picture = picture.convert("RGB")

            output = BytesIO()

            picture.save(
                output,
                format="JPEG",
                quality=85
            )

            output.seek(0)

            embed["image"] = {
                "url": "attachment://cod_news.jpg"
            }

            response = session.post(
                WEBHOOK,
                data={
                    "payload_json": json.dumps({
                        "embeds": [embed]
                    })
                },
                files={
                    "files[0]": (
                        "cod_news.jpg",
                        output,
                        "image/jpeg"
                    )
                },
                timeout=(5, 30)
            )

            response.raise_for_status()
            return

        except (requests.RequestException, OSError, ValueError) as error:
            print(
                "Immagine non disponibile:",
                error,
                flush=True
            )
            embed.pop("image", None)

    response = session.post(
        WEBHOOK,
        json={"embeds": [embed]},
        timeout=(5, 15)
    )

    response.raise_for_status()


def main():
    articles, errors = get_articles()

    if not articles:
        raise RuntimeError("Nessun articolo valido")

    if errors:
        raise RuntimeError(
            "Alcuni articoli non sono stati letti. "
            "Nessuna pubblicazione o modifica allo storico."
        )

    if STATE.exists():
        seen = set(
            json.loads(
                STATE.read_text(encoding="utf-8")
            )
        )

        selected = [
            a for a in articles
            if a["url"] not in seen
        ]
    else:
        seen = set()
        selected = articles[:3]

    print(
        "\nNOTIZIE SELEZIONATE:",
        len(selected)
    )

    for article in reversed(selected):
        print(
            "NOTIZIA:",
            article["date"].isoformat(),
            article["title"],
            flush=True
        )

        if not DRY_RUN:
            send_discord(article)
            time.sleep(2)

    if DRY_RUN:
        print(
            "SIMULAZIONE: nessun messaggio inviato",
            flush=True
        )
        return

    seen.update(
        a["url"] for a in articles
    )

    STATE.write_text(
        json.dumps(sorted(seen), indent=2),
        encoding="utf-8"
    )

    print("Storico aggiornato", flush=True)


if __name__ == "__main__":
    main()
