import os
import re
import json
import time
import html
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

# ARTYKO MMO NEWS V5 - MMO.it
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "mmo_seen_articles.json"
COVER_FILE = BASE_DIR / "mmo_cover.png"
WEBHOOK = os.getenv("DISCORD_WEBHOOK_MMO", "")
DRY_RUN = os.getenv("MMO_DRY_RUN", "true").lower() != "false"
SOURCE_URL = "https://www.mmo.it/"
ITALY_TZ = ZoneInfo("Europe/Rome")
DAILY_LIMIT = 2
MAX_PER_RUN = 2

MMO_KEYWORDS = (
    "mmorpg", "mmo", "world of warcraft", "wow classic", "warcraft",
    "aion", "final fantasy xiv", "ffxiv", "guild wars", "elder scrolls online",
    "black desert", "runescape", "ashes of creation", "chrono odyssey",
    "archeage", "throne and liberty", "lost ark", "new world", "eve online",
    "albion online", "blade and soul", "maplestory", "lineage", "blue protocol",
    "pax dei", "star citizen", "pantheon", "everquest", "dune awakening",
    "once human", "soulframe", "the quinfall", "corepunk", "project gorgon",
    "tower of fantasy", "warframe", "fractured online", "ultima online",
    "broken ranks", "rune scape", "archeage chronicles"
)
EXCLUDED_KEYWORDS = (
    "fortnite", "valorant", "counter-strike", "call of duty", "apex legends",
    "overwatch", "league of legends", "marvel rivals", "recensione",
    "review", "sconti", "offerte", "coupon"
)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ARTYKO-MMO-News/5.0)"})


def clean_text(value):
    if hasattr(value, "get_text"):
        value = value.get_text(" ", strip=True)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())


def article_key(url):
    p = urlsplit(url.strip())
    canonical = urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def italy_today():
    return datetime.now(ITALY_TZ).date().isoformat()


def load_state():
    if not STATE_FILE.exists():
        return {"seen": [], "daily_counts": {}}
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"seen": data, "daily_counts": {}}
    if not isinstance(data, dict) or not isinstance(data.get("seen", []), list) or not isinstance(data.get("daily_counts", {}), dict):
        raise ValueError("Storico MMO non valido")
    return {"seen": data.get("seen", []), "daily_counts": data.get("daily_counts", {})}


def save_state(state):
    temporary = STATE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATE_FILE)


def contains_any(text, keywords):
    return any(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text) for word in keywords)


def is_relevant(article):
    title = article["title"].lower()
    if contains_any(title, EXCLUDED_KEYWORDS):
        return False
    return contains_any(title, MMO_KEYWORDS)


def fetch_articles():
    response = session.get(SOURCE_URL, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    articles = []
    known = set()

    # I titoli degli articoli compaiono in intestazioni della pagina.
    # Non leggiamo le notizie 'in evidenza' per evitare vecchi post riproposti.
    for heading in soup.select("h2, h3"):
        link = heading.find("a", href=True)
        if not link:
            continue
        title = clean_text(link)
        url = urljoin(SOURCE_URL, link["href"])
        parts = urlsplit(url)
        if parts.netloc.lower() not in ("mmo.it", "www.mmo.it"):
            continue
        if not re.search(r"/20\d{2}/\d{2}/\d{2}/", parts.path):
            continue
        if len(title) < 12:
            continue
        key = article_key(url)
        if key in known:
            continue
        known.add(key)

        # Preferiamo l'estratto dell'articolo; niente testo preso dalla sidebar.
        block = heading.find_parent("article")
        if block is None:
            block = heading.find_parent(class_=re.compile(r"post|entry", re.I))
        description = ""
        if block:
            excerpt = block.select_one(".entry-summary, .post-excerpt, .entry-content, .excerpt")
            if excerpt:
                description = clean_text(excerpt)
            else:
                paragraph = block.find("p")
                if paragraph:
                    description = clean_text(paragraph)
        article = {
            "id": key,
            "title": title,
            "url": url,
            "description": description[:350],
            "source": "MMO.it",
        }
        if is_relevant(article):
            articles.append(article)

    print("MMO.it - articoli pertinenti:", len(articles), flush=True)
    if not articles:
        raise RuntimeError("Nessun articolo MMO trovato: verificare struttura HTML di MMO.it")
    return articles


def publish_article(article):
    if not WEBHOOK:
        raise RuntimeError("Secret DISCORD_WEBHOOK_MMO mancante")
    if not COVER_FILE.is_file():
        raise RuntimeError("Copertina mmo_cover.png mancante")
    embed = {
        "title": article["title"][:256],
        "url": article["url"],
        "description": article["description"][:350],
        "color": 0x00D9B5,
        "image": {"url": "attachment://mmo_cover.png"},
        "footer": {"text": "ARTYKO MMO NEWS | MMO.it"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload = {"username": "ARTYKO MMO NEWS", "embeds": [embed]}
    with COVER_FILE.open("rb") as cover:
        response = session.post(
            WEBHOOK,
            data={"payload_json": json.dumps(payload)},
            files={"files[0]": ("mmo_cover.png", cover, "image/png")},
            timeout=30,
        )
    response.raise_for_status()


def main():
    print("=== ARTYKO MMO NEWS V5 ITALIA ===", flush=True)
    print("Fonte: MMO.it", flush=True)
    print("Simulazione:", DRY_RUN, flush=True)
    state = load_state()
    seen = set(state["seen"])
    daily_counts = state["daily_counts"]
    today = italy_today()
    remaining = max(0, DAILY_LIMIT - int(daily_counts.get(today, 0)))
    print("Data italiana:", today, flush=True)
    print("Post gia' pubblicati oggi:", daily_counts.get(today, 0), flush=True)
    print("Post disponibili:", remaining, flush=True)
    if remaining == 0:
        print("Limite giornaliero raggiunto.", flush=True)
        return
    articles = fetch_articles()
    new_articles = [article for article in articles if article["id"] not in seen]
    selected = new_articles[:min(MAX_PER_RUN, remaining)]
    print("Nuove notizie:", len(new_articles), flush=True)
    print("Notizie pronte:", len(selected), flush=True)
    for article in selected:
        print("[MMO.it]", article["title"], flush=True)
        print(article["url"], flush=True)
        print("Estratto:", article["description"][:120], flush=True)
    if DRY_RUN:
        print("SIMULAZIONE COMPLETATA. Nessun messaggio pubblicato.", flush=True)
        return
    for article in selected:
        publish_date = italy_today()
        if int(daily_counts.get(publish_date, 0)) >= DAILY_LIMIT:
            print("Limite del giorno raggiunto.", flush=True)
            break
        publish_article(article)
        seen.add(article["id"])
        daily_counts[publish_date] = int(daily_counts.get(publish_date, 0)) + 1
        daily_counts = {day: daily_counts[day] for day in sorted(daily_counts)[-30:]}
        state["seen"] = sorted(seen)
        state["daily_counts"] = daily_counts
        save_state(state)
        print("PUBBLICATO:", article["title"], flush=True)
        time.sleep(2)
    print("ARTYKO MMO NEWS completato.", flush=True)


if __name__ == "__main__":
    main()
