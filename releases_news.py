
import os
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# ============================================
# ARTYKO GAME RELEASES
# Calendario giornaliero videogiochi
# ============================================

WEBHOOK = os.getenv("DISCORD_WEBHOOK_RELEASES", "")
DRY_RUN = os.getenv("RELEASES_DRY_RUN", "true").lower() != "false"

TIMEZONE = ZoneInfo("Europe/Rome")
NOW = datetime.now(TIMEZONE)
TODAY = NOW.date()
END_DATE = TODAY + timedelta(days=6)

COVER = Path("releases_cover.png")
HISTORY = Path("releases_seen.json")

STEAM_URL = (
    "https://store.steampowered.com/search/"
    "?filter=popularcomingsoon&supportedlang=english"
)

MAX_PAGES = 5
MAX_GAMES = 12

HEADERS = {
    "User-Agent": "Mozilla/5.0 ARTYKO-Game-Releases/1.0",
    "Accept-Language": "en-US,en;q=0.9",
}

PRIORITY_WORDS = (
    "mmorpg", "massively multiplayer", "rpg",
    "role-playing", "multiplayer", "online",
    "action", "adventure", "open world",
    "survival", "shooter", "strategy",
)

EXCLUDED_WORDS = (
    "demo", "soundtrack", "artbook",
    "art book", "wallpaper", "playtest",
    "dedicated server",
)


def parse_date(raw):
    """Accetta soltanto date complete e non ambigue."""
    raw = re.sub(r"\s+", " ", raw or "").strip()
    raw = re.sub(r"(?i)^release date:\s*", "", raw)

    formats = (
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b, %Y",
        "%d %B, %Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    return None


def load_history():
    if not HISTORY.exists():
        return {}

    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def save_history(history):
    HISTORY.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_steam_games():
    """Legge le prossime uscite popolari di Steam."""
    session = requests.Session()
    session.headers.update(HEADERS)

    games = {}
    successful_pages = 0

    for page in range(MAX_PAGES):
        params = {
            "query": "",
            "start": page * 50,
            "count": 50,
            "dynamic_data": "",
            "sort_by": "_ASC",
            "filter": "popularcomingsoon",
            "supportedlang": "english",
            "infinite": "1",
        }

        try:
            response = session.get(
                "https://store.steampowered.com/search/results/",
                params=params,
                timeout=25,
            )
            response.raise_for_status()

            payload = response.json()
            html = payload.get("results_html", "")
            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("a.search_result_row")

            successful_pages += 1
            print(f"Steam pagina {page + 1}: {len(rows)} risultati")

            if not rows:
                break

            for row in rows:
                appid = row.get("data-ds-appid", "").split(",")[0]
                title_el = row.select_one(".title")
                date_el = row.select_one(".search_released")

                if not appid.isdigit() or not title_el or not date_el:
                    continue

                title = title_el.get_text(" ", strip=True)
                release = parse_date(date_el.get_text(" ", strip=True))

                if not release or not TODAY <= release <= END_DATE:
                    continue

                if any(word in title.lower() for word in EXCLUDED_WORDS):
                    continue

                url = f"https://store.steampowered.com/app/{appid}/"

                games[appid] = {
                    "id": appid,
                    "title": title,
                    "date": release,
                    "url": url,
                    "platform": "PC (Steam)",
                }

            time.sleep(0.5)

        except (requests.RequestException, ValueError) as exc:
            print(f"Errore Steam pagina {page + 1}: {exc}")
            continue

    if successful_pages == 0:
        raise RuntimeError("Steam non ha restituito pagine utilizzabili.")

    return list(games.values())


def priority_score(game):
    """Priorità indicativa, non classificazione AAA certificata."""
    title = game["title"].lower()

    score = 0

    for word in PRIORITY_WORDS:
        if word in title:
            score += 2

    return score


def build_message(games):
    ordered = sorted(
        games,
        key=lambda game: (
            game["date"],
            -priority_score(game),
            game["title"].lower(),
        ),
    )[:MAX_GAMES]

    lines = []

    for game in ordered:
        date_text = game["date"].strftime("%d/%m/%Y")
        lines.append(
            f"🎮 **[{game['title']}]({game['url']})**\n"
            f"📅 {date_text} · 💻 {game['platform']}"
        )

    description = "\n\n".join(lines)

    if len(description) > 3900:
        description = description[:3850] + "\n\n…"

    return {
        "username": "ARTYKO GAME RELEASES",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": "🎮 ARTYKO | USCITE VIDEOGIOCHI",
                "description": description,
                "color": 0x00E5C3,
                "fields": [
                    {
                        "name": "📅 Periodo",
                        "value": (
                            f"{TODAY.strftime('%d/%m/%Y')} — "
                            f"{END_DATE.strftime('%d/%m/%Y')}"
                        ),
                        "inline": False,
                    }
                ],
                "footer": {
                    "text": (
                        "Fonte: Steam · Date soggette a modifiche "
                        "· Copertura PC parziale"
                    )
                },
                "timestamp": NOW.isoformat(),
            }
        ],
    }


def publish(payload):
    if not WEBHOOK:
        raise RuntimeError("Secret DISCORD_WEBHOOK_RELEASES mancante.")

    url = WEBHOOK + ("&" if "?" in WEBHOOK else "?") + "wait=true"

    if COVER.is_file():
        payload["embeds"][0]["image"] = {
            "url": "attachment://releases_cover.png"
        }

        with COVER.open("rb") as image:
            response = requests.post(
                url,
                data={"payload_json": json.dumps(payload)},
                files={
                    "files[0]": (
                        "releases_cover.png",
                        image,
                        "image/png",
                    )
                },
                timeout=30,
            )
    else:
        print("Copertina assente: invio senza immagine.")
        response = requests.post(url, json=payload, timeout=30)

    response.raise_for_status()
    print("Messaggio pubblicato su Discord.")


def main():
    print("======================================")
    print("ARTYKO GAME RELEASES")
    print("======================================")
    print(f"Ora italiana: {NOW.isoformat()}")
    print(f"Periodo: {TODAY} -> {END_DATE}")
    print(f"Modalità simulazione: {DRY_RUN}")

    history = load_history()
    today_key = TODAY.isoformat()

    if history.get("last_published") == today_key:
        print("Calendario già pubblicato oggi.")
        return

    games = get_steam_games()
    print(f"Giochi con data valida nei prossimi 7 giorni: {len(games)}")

    if not games:
        print("Nessuna uscita verificata nel campione Steam.")
        print("Nessun messaggio inviato.")
        return

    payload = build_message(games)

    print("\nANTEPRIMA CALENDARIO:")
    print(payload["embeds"][0]["description"])

    if DRY_RUN:
        print("\nSIMULAZIONE COMPLETATA.")
        print("Nessun messaggio pubblicato.")
        return

    publish(payload)

    history["last_published"] = today_key
    save_history(history)
    print("Storico aggiornato.")


if __name__ == "__main__":
    main()
