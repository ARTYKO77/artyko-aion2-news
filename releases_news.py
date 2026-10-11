
import os
import re
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# ============================================
# ARTYKO GAME RELEASES V3
# STEAM + GAMESRADAR MULTIPIATTAFORMA
# ============================================

BASE_DIR = Path(__file__).resolve().parent

WEBHOOK = os.getenv("DISCORD_WEBHOOK_RELEASES", "")
DRY_RUN = os.getenv(
    "RELEASES_DRY_RUN", "true"
).lower() != "false"

TZ = ZoneInfo("Europe/Rome")
NOW = datetime.now(TZ)
TODAY = NOW.date()

WATCHLIST = BASE_DIR / "releases_watchlist.json"
SOURCES = BASE_DIR / "releases_sources.json"
HISTORY = BASE_DIR / "releases_seen.json"
COVER = BASE_DIR / "releases_cover.png"

MAX_STEAM_PAGES = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = {
    name.upper(): number
    for number, name in enumerate(
        [
            "January", "February", "March",
            "April", "May", "June",
            "July", "August", "September",
            "October", "November", "December"
        ],
        start=1,
    )
}

ENTRY_PATTERN = re.compile(
    r"^(.+?)\s+[-–—]\s+"
    r"([A-Za-z]+)\s+(\d{1,2})"
    r"(?:,\s*(20\d{2}))?"
    r"(?:\s+\[([^\]]+)\])?\s*$"
)

PLATFORM_PATTERN = re.compile(
    r"^(.*?)\s*\(([^()]*)\)$"
)

EXCLUDED = (
    "demo", "playtest", "soundtrack",
    "artbook", "art book", "wallpaper",
    "dedicated server", "beta test",
    "test server",
)

EDITION_TERMS = (
    "deluxe edition", "gold edition",
    "ultimate edition", "complete edition",
    "remastered", "remake", "definitive edition",
    "anniversary edition",
)

MAJOR_TERMS = (
    "resident evil", "final fantasy",
    "warhammer", "call of duty",
    "battlefield", "grand theft auto",
    "gta", "assassin s creed",
    "monster hunter", "silent hill",
    "the witcher", "gears of war",
    "doom", "elder scrolls",
    "fable", "dragon quest",
    "kingdom hearts", "mass effect",
    "star wars", "zelda", "pokemon",
    "mario", "minecraft", "diablo",
    "world of warcraft", "aion",
    "tomb raider", "metal gear",
    "forza", "halo", "stalker",
    "cyberpunk", "borderlands",
)

session = requests.Session()
session.headers.update(HEADERS)


def normalize(value):
    return " ".join(
        re.sub(
            r"[^a-z0-9]+", " ",
            (value or "").casefold()
        ).split()
    )


def load_json(path, default):
    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return default


def load_watchlist():
    data = load_json(WATCHLIST, {})
    titles = data.get("priority_games", [])

    return [
        normalize(title)
        for title in titles
        if isinstance(title, str)
    ]


def load_config():
    config = load_json(SOURCES, {})

    if not config:
        raise RuntimeError(
            "releases_sources.json mancante o non valido."
        )

    days = int(config.get("days_ahead", 7))
    max_games = int(config.get("max_games", 10))

    if not 1 <= days <= 31:
        raise ValueError("days_ahead non valido.")

    if not 1 <= max_games <= 10:
        raise ValueError("max_games deve essere tra 1 e 10.")

    return config, days, max_games


def load_history():
    return load_json(HISTORY, {})


def save_history(data):
    HISTORY.write_text(
        json.dumps(
            data, indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def is_excluded(title):
    text = normalize(title)
    return any(
        re.search(
            rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])",
            text
        )
        for term in EXCLUDED
    )


def is_priority(title, watchlist):
    text = normalize(title)

    return any(
        text == item
        or text.startswith(item + " ")
        for item in watchlist
        if item
    )


def score_game(game, watchlist):
    title = normalize(game["title"])

    score = 0

    if is_priority(game["title"], watchlist):
        score += 100

    if any(term in title for term in MAJOR_TERMS):
        score += 40

    if "GamesRadar" in game["sources"]:
        score += 20

    if "Steam" in game["sources"]:
        score += 10

    if game["platforms"] != "PC":
        score += 5

    if any(term in title for term in EDITION_TERMS):
        score -= 15

    return score


def parse_steam_date(value):
    value = re.sub(
        r"\s+", " ", value or ""
    ).strip()

    for fmt in (
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b, %Y",
        "%d %B, %Y",
    ):
        try:
            return datetime.strptime(
                value, fmt
            ).date()
        except ValueError:
            pass

    return None


def fetch_steam(today, end_date):
    games = []
    successful_pages = 0

    for page in range(MAX_STEAM_PAGES):
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

            rows = BeautifulSoup(
                response.json().get(
                    "results_html", ""
                ),
                "html.parser"
            ).select("a.search_result_row")

            successful_pages += 1
            print(
                f"Steam pagina {page + 1}: "
                f"{len(rows)} giochi"
            )

            if not rows:
                break

            for row in rows:
                appid = row.get(
                    "data-ds-appid", ""
                ).split(",")[0]

                title_element = row.select_one(
                    ".title"
                )
                date_element = row.select_one(
                    ".search_released"
                )

                if not (
                    appid.isdigit()
                    and title_element
                    and date_element
                ):
                    continue

                title = title_element.get_text(
                    " ", strip=True
                )

                if is_excluded(title):
                    continue

                release_date = parse_steam_date(
                    date_element.get_text(
                        " ", strip=True
                    )
                )

                if (
                    release_date is None
                    or not today <= release_date <= end_date
                ):
                    continue

                games.append({
                    "title": title,
                    "date": release_date,
                    "platforms": "PC",
                    "url": (
                        "https://store.steampowered.com/"
                        f"app/{appid}/"
                    ),
                    "sources": ["Steam"],
                    "note": "",
                    "officially_verified": False,
                })

            time.sleep(0.2)

        except (requests.RequestException, ValueError) as exc:
            print(
                f"Errore Steam pagina {page + 1}: {exc}"
            )

    if successful_pages == 0:
        print(
            "ATTENZIONE: Steam non disponibile."
        )

    return games


def fetch_gamesradar(config, today, end_date):
    source = next(
        (
            item
            for item in config.get(
                "editorial_sources", []
            )
            if (
                item.get("name") == "GamesRadar"
                and item.get("enabled")
            )
        ),
        None,
    )

    if source is None:
        return []

    response = session.get(
        source["url"], timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text, "html.parser"
    )

    games = []

    for heading in soup.select("h2, h3"):
        heading_text = heading.get_text(
            " ", strip=True
        ).upper()

        if "GAMES OF" not in heading_text:
            continue

        month_name = next(
            (
                name for name in MONTHS
                if re.search(
                    rf"\b{name}\b",
                    heading_text
                )
            ),
            None,
        )

        year_match = re.search(
            r"\b20\d{2}\b", heading_text
        )

        if not month_name or not year_match:
            continue

        section_year = int(
            year_match.group()
        )
        section_month = MONTHS[month_name]

        month_index = (
            section_year * 12
            + section_month
        )
        start_index = (
            today.year * 12
            + today.month
        )
        end_index = (
            end_date.year * 12
            + end_date.month
        )

        if not (
            start_index <= month_index <= end_index
        ):
            continue

        sibling = heading.find_next_sibling()

        while sibling and sibling.name not in (
            "h2", "h3"
        ):
            if sibling.name in ("ul", "ol"):
                for li in sibling.find_all(
                    "li", recursive=False
                ):
                    text = li.get_text(
                        " ", strip=True
                    )

                    match = ENTRY_PATTERN.match(
                        text
                    )

                    if not match:
                        continue

                    info, month_text, day, year_text, note = (
                        match.groups()
                    )

                    month_number = MONTHS.get(
                        month_text.upper()
                    )

                    if not month_number:
                        continue

                    year = int(
                        year_text or section_year
                    )

                    try:
                        release_date = datetime(
                            year, month_number,
                            int(day)
                        ).date()
                    except ValueError:
                        continue

                    if not (
                        today <= release_date <= end_date
                    ):
                        continue

                    platform_match = (
                        PLATFORM_PATTERN.match(
                            info.strip()
                        )
                    )

                    if platform_match:
                        title = platform_match.group(
                            1
                        ).strip()
                        platforms = platform_match.group(
                            2
                        ).strip()
                    else:
                        title = info.strip()
                        platforms = "Non specificate"

                    if is_excluded(title):
                        continue

                    games.append({
                        "title": title,
                        "date": release_date,
                        "platforms": platforms,
                        "url": source["url"],
                        "sources": ["GamesRadar"],
                        "note": note or "",
                        "officially_verified": False,
                    })

            sibling = sibling.find_next_sibling()

    print(
        "GamesRadar: ",
        len(games),
        "uscite nel periodo"
    )

    return games


def merge_games(games):
    merged = {}

    for game in games:
        key = (
            normalize(game["title"]),
            game["date"].isoformat()
        )

        if key not in merged:
            merged[key] = game.copy()
            continue

        existing = merged[key]

        for source in game["sources"]:
            if source not in existing["sources"]:
                existing["sources"].append(source)

        # Mantiene la lista di piattaforme piu' ampia.
        if len(game["platforms"]) > len(
            existing["platforms"]
        ):
            existing["platforms"] = game["platforms"]

        # Preferisce un collegamento Steam
        # rispetto alla pagina generale.
        if "store.steampowered.com" in game["url"]:
            existing["url"] = game["url"]

        if game["note"] and not existing["note"]:
            existing["note"] = game["note"]

    return list(merged.values())


def select_games(games, watchlist, max_games):
    ranked = sorted(
        games,
        key=lambda game: (
            -score_game(game, watchlist),
            game["date"],
            game["title"].casefold(),
        )
    )

    return sorted(
        ranked[:max_games],
        key=lambda game: (
            game["date"],
            game["title"].casefold(),
        )
    )


def build_payload(games, today, end_date):
    entries = []

    for game in games:
        date_text = game["date"].strftime(
            "%d/%m/%Y"
        )

        sources = " + ".join(
            game["sources"]
        )

        note = (
            f" · {game['note']}"
            if game["note"] else ""
        )

        entries.append(
            f"🎮 **[{game['title']}]({game['url']})**\n"
            f"📅 {date_text} · "
            f"🎯 {game['platforms']}{note}\n"
            f"🔎 Fonte: {sources}"
        )

    description = "\n\n".join(entries)

    return {
        "username": "ARTYKO GAME RELEASES",
        "allowed_mentions": {
            "parse": []
        },
        "embeds": [
            {
                "title": (
                    "🎮 ARTYKO | "
                    "USCITE DEI PROSSIMI 7 GIORNI"
                ),
                "description": description[:4000],
                "color": 0x00E5C3,
                "fields": [
                    {
                        "name": "📅 Periodo",
                        "value": (
                            f"{today.strftime('%d/%m/%Y')}"
                            " — "
                            f"{end_date.strftime('%d/%m/%Y')}"
                        ),
                        "inline": False,
                    }
                ],
                "footer": {
                    "text": (
                        "Fonti: Steam / GamesRadar"
                        " · Date da verificare sui siti ufficiali"
                    )
                },
                "timestamp": NOW.isoformat(),
            }
        ],
    }


def publish(payload):
    if not WEBHOOK:
        raise RuntimeError(
            "Secret DISCORD_WEBHOOK_RELEASES mancante."
        )

    url = WEBHOOK + (
        "&" if "?" in WEBHOOK else "?"
    ) + "wait=true"

    if COVER.exists():
        payload["embeds"][0]["image"] = {
            "url": "attachment://releases_cover.png"
        }

        with COVER.open("rb") as image:
            response = session.post(
                url,
                data={
                    "payload_json": json.dumps(
                        payload
                    )
                },
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
        response = session.post(
            url, json=payload, timeout=30
        )

    response.raise_for_status()
    print(
        "Calendario pubblicato su Discord."
    )


def main():
    config, days, max_games = load_config()

    today = TODAY
    end_date = today + timedelta(
        days=days - 1
    )

    print("====================================")
    print("ARTYKO GAME RELEASES V3")
    print("====================================")
    print("Ora italiana:", NOW.isoformat())
    print("Periodo:", today, "-", end_date)
    print("Simulazione:", DRY_RUN)

    watchlist = load_watchlist()
    print(
        "Titoli prioritari:",
        len(watchlist)
    )

    history = load_history()

    if history.get(
        "last_published"
    ) == today.isoformat():
        print(
            "Calendario gia' pubblicato oggi."
        )
        return

    all_games = []

    try:
        all_games.extend(
            fetch_gamesradar(
                config, today, end_date
            )
        )
    except (
        requests.RequestException,
        ValueError
    ) as exc:
        print(
            "ERRORE GamesRadar:", exc
        )

    all_games.extend(
        fetch_steam(today, end_date)
    )

    merged = merge_games(all_games)

    print(
        "Uscite complessive:",
        len(merged)
    )

    if not merged:
        print(
            "Nessuna uscita nei prossimi giorni."
        )
        print(
            "Nessun messaggio inviato."
        )
        return

    selected = select_games(
        merged, watchlist, max_games
    )

    print("\nCALENDARIO SELEZIONATO:")

    for game in selected:
        print(
            game["date"],
            "|", game["title"],
            "|", game["platforms"],
            "|", "+".join(
                game["sources"]
            ),
            "| score:",
            score_game(game, watchlist),
        )

    payload = build_payload(
        selected, today, end_date
    )

    print("\nANTEPRIMA DISCORD:")
    print(
        payload["embeds"][0]["description"]
    )

    if DRY_RUN:
        print(
            "\nSIMULAZIONE COMPLETATA."
        )
        print(
            "Nessun messaggio pubblicato."
        )
        return

    publish(payload)
    history["last_published"] = (
        today.isoformat()
    )
    save_history(history)

    print("Storico aggiornato.")


if __name__ == "__main__":
    main()
