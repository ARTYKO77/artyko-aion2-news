
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
# ARTYKO GAME RELEASES - V2
# Calendario curato, con watchlist
# ============================================

WEBHOOK = os.getenv("DISCORD_WEBHOOK_RELEASES", "")
DRY_RUN = os.getenv("RELEASES_DRY_RUN", "true").lower() != "false"

TZ = ZoneInfo("Europe/Rome")
NOW = datetime.now(TZ)
TODAY = NOW.date()
END_DATE = TODAY + timedelta(days=6)

WATCHLIST = Path("releases_watchlist.json")
HISTORY = Path("releases_seen.json")
COVER = Path("releases_cover.png")

MAX_PAGES = 10
MAX_GAMES = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}

EXCLUDED = (
    "demo", "playtest", "soundtrack", "artbook",
    "art book", "wallpaper", "dedicated server",
    "beta test", "test server",
)


def normalize(text):
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def load_watchlist():
    if not WATCHLIST.exists():
        raise RuntimeError("File releases_watchlist.json mancante.")

    data = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    titles = data.get("priority_games", [])

    if not isinstance(titles, list) or not titles:
        raise RuntimeError("Watchlist vuota o non valida.")

    return [normalize(x) for x in titles if isinstance(x, str)]


def parse_date(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    value = re.sub(r"(?i)^release date:\s*", "", value)

    for fmt in (
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b, %Y",
        "%d %B, %Y",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def load_history():
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_history(data):
    HISTORY.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_priority(title, watchlist):
    normalized = normalize(title)

    for entry in watchlist:
        if normalized == entry:
            return True

        # Consente sottotitoli ed edizioni dei giochi monitorati.
        if normalized.startswith(entry + " "):
            return True

    return False


def fetch_games(watchlist):
    session = requests.Session()
    session.headers.update(HEADERS)

    selected = {}
    successful_pages = 0

    for page in range(MAX_PAGES):
        try:
            response = session.get(
                "https://store.steampowered.com/search/results/",
                params={
                    "start": page * 50,
                    "count": 50,
                    "filter": "popularcomingsoon",
                    "supportedlang": "english",
                    "infinite": "1",
                },
                timeout=25,
            )
            response.raise_for_status()

            html = response.json().get("results_html", "")
            rows = BeautifulSoup(
                html, "html.parser"
            ).select("a.search_result_row")

            successful_pages += 1
            print(f"Steam pagina {page + 1}: {len(rows)} giochi")

            if not rows:
                break

            for row in rows:
                appid = row.get("data-ds-appid", "").split(",")[0]
                title_element = row.select_one(".title")
                date_element = row.select_one(".search_released")

                if not appid.isdigit() or not title_element or not date_element:
                    continue

                title = title_element.get_text(" ", strip=True)

                if any(word in normalize(title) for word in EXCLUDED):
                    continue

                if not is_priority(title, watchlist):
                    continue

                release = parse_date(
                    date_element.get_text(" ", strip=True)
                )

                if release is None or not TODAY <= release <= END_DATE:
                    continue

                selected[appid] = {
                    "title": title,
                    "date": release,
                    "url": f"https://store.steampowered.com/app/{appid}/",
                }

            time.sleep(0.3)

        except (requests.RequestException, ValueError) as exc:
            print(f"Errore pagina {page + 1}: {exc}")

    if successful_pages == 0:
        raise RuntimeError("Impossibile leggere il catalogo Steam.")

    return sorted(
        selected.values(),
        key=lambda x: (x["date"], x["title"].casefold()),
    )[:MAX_GAMES]


def build_payload(games):
    entries = []

    for game in games:
        date_text = game["date"].strftime("%d/%m/%Y")
        entries.append(
            f"🎮 **[{game['title']}]({game['url']})**\n"
            f"📅 {date_text} · 💻 PC (Steam)"
        )

    return {
        "username": "ARTYKO GAME RELEASES",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": "🎮 ARTYKO | PROSSIME USCITE",
                "description": "\n\n".join(entries),
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
                    "text": "Fonte: Steam · Calendario PC selezionato"
                },
                "timestamp": NOW.isoformat(),
            }
        ],
    }


def publish(payload):
    if not WEBHOOK:
        raise RuntimeError("Secret DISCORD_WEBHOOK_RELEASES mancante.")

    url = WEBHOOK + ("&" if "?" in WEBHOOK else "?") + "wait=true"

    if COVER.exists():
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
        response = requests.post(url, json=payload, timeout=30)

    response.raise_for_status()
    print("Calendario pubblicato su Discord.")


def main():
    print("====================================")
    print("ARTYKO GAME RELEASES V2")
    print("====================================")
    print(f"Ora italiana: {NOW.isoformat()}")
    print(f"Periodo: {TODAY} - {END_DATE}")
    print(f"Simulazione: {DRY_RUN}")

    watchlist = load_watchlist()
    print(f"Titoli prioritari: {len(watchlist)}")

    history = load_history()

    if history.get("last_published") == TODAY.isoformat():
        print("Calendario già pubblicato oggi.")
        return

    games = fetch_games(watchlist)

    print(f"Uscite prioritarie trovate: {len(games)}")

    if not games:
        print("Nessuna uscita prioritaria nei prossimi 7 giorni.")
        print("Nessun messaggio inviato.")
        return

    payload = build_payload(games)

    print("\nANTEPRIMA:")
    print(payload["embeds"][0]["description"])

    if DRY_RUN:
        print("\nSIMULAZIONE COMPLETATA.")
        print("Nessun messaggio pubblicato.")
        return

    publish(payload)
    history["last_published"] = TODAY.isoformat()
    save_history(history)
    print("Storico aggiornato.")


if __name__ == "__main__":
    main()
