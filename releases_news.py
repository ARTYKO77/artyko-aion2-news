
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# ============================================
# ARTYKO GAME RELEASES V4 - PREMIUM DRY RUN
# Nessuna pubblicazione Discord
# ============================================

ROOT = Path(__file__).resolve().parent
TZ = ZoneInfo("Europe/Rome")
NOW = datetime.now(TZ)
TODAY = NOW.date()

PREMIUM_FILE = ROOT / "releases_premium.json"
SOURCES_FILE = ROOT / "releases_sources.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = {
    name.upper(): index
    for index, name in enumerate(
        [
            "January", "February", "March",
            "April", "May", "June",
            "July", "August", "September",
            "October", "November", "December",
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

EXCLUDED_CONTENT = (
    "demo",
    "playtest",
    "soundtrack",
    "artbook",
    "art book",
    "wallpaper",
    "dedicated server",
    "beta test",
    "test server",
)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def normalize(value):
    value = (value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"File obbligatorio mancante: {path.name}"
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Formato JSON non valido: {path.name}"
        )

    return data


def phrase_matches(title, phrase):
    title_words = normalize(title).split()
    phrase_words = normalize(phrase).split()

    if not phrase_words:
        return False

    size = len(phrase_words)

    return any(
        title_words[i:i + size] == phrase_words
        for i in range(
            len(title_words) - size + 1
        )
    )


def matches_any(title, phrases):
    return any(
        phrase_matches(title, phrase)
        for phrase in phrases
        if isinstance(phrase, str)
    )


def is_excluded(title, premium):
    if matches_any(title, EXCLUDED_CONTENT):
        return True

    return matches_any(
        title,
        premium.get("exclude_editions", [])
    )


def premium_category(title, premium):
    if matches_any(
        title,
        premium.get("approved_games", [])
    ):
        return "Titolo approvato"

    if matches_any(
        title,
        premium.get("major_mmos", [])
    ):
        return "MMORPG / MMO"

    if matches_any(
        title,
        premium.get("major_franchises", [])
    ):
        return "Grande franchise"

    return None


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
            continue

    return None


def fetch_steam(today, end_date):
    games = []
    pages_ok = 0

    for page in range(10):
        try:
            response = SESSION.get(
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

            html = response.json().get(
                "results_html", ""
            )

            rows = BeautifulSoup(
                html, "html.parser"
            ).select("a.search_result_row")

            pages_ok += 1

            print(
                f"Steam pagina {page + 1}: "
                f"{len(rows)} giochi"
            )

            if not rows:
                break

            for row in rows:
                appid = str(
                    row.get("data-ds-appid", "")
                ).split(",")[0]

                title_node = row.select_one(
                    ".title"
                )
                date_node = row.select_one(
                    ".search_released"
                )

                if not (
                    appid.isdigit()
                    and title_node
                    and date_node
                ):
                    continue

                title = title_node.get_text(
                    " ", strip=True
                )

                release_date = parse_steam_date(
                    date_node.get_text(
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
                })

            time.sleep(0.2)

        except (
            requests.RequestException,
            ValueError,
        ) as exc:
            print(
                f"Errore Steam pagina {page + 1}: "
                f"{exc}"
            )

    if pages_ok == 0:
        print(
            "ATTENZIONE: Steam non disponibile."
        )

    return games


def fetch_gamesradar(config, today, end_date):
    sources = config.get(
        "editorial_sources", []
    )

    source = next(
        (
            item for item in sources
            if (
                item.get("name") == "GamesRadar"
                and item.get("enabled")
            )
        ),
        None,
    )

    if not source:
        print("GamesRadar disabilitato.")
        return []

    response = SESSION.get(
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
            r"\b20\d{2}\b",
            heading_text
        )

        if not month_name or not year_match:
            continue

        section_year = int(
            year_match.group()
        )
        section_month = MONTHS[month_name]

        month_index = (
            section_year * 12 + section_month
        )
        start_index = (
            today.year * 12 + today.month
        )
        end_index = (
            end_date.year * 12 + end_date.month
        )

        if not (
            start_index <= month_index <= end_index
        ):
            continue

        sibling = heading.find_next_sibling()

        while (
            sibling
            and sibling.name not in ("h2", "h3")
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

                    (
                        info,
                        month_text,
                        day_text,
                        year_text,
                        note,
                    ) = match.groups()

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
                            year,
                            month_number,
                            int(day_text),
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
                        title = (
                            platform_match.group(1)
                            .strip()
                        )
                        platforms = (
                            platform_match.group(2)
                            .strip()
                        )
                    else:
                        title = info.strip()
                        platforms = (
                            "Non specificate"
                        )

                    games.append({
                        "title": title,
                        "date": release_date,
                        "platforms": platforms,
                        "url": source["url"],
                        "sources": ["GamesRadar"],
                        "note": note or "",
                    })

            sibling = sibling.find_next_sibling()

    print(
        f"GamesRadar: {len(games)} "
        "uscite nel periodo"
    )

    return games


def merge_games(games):
    merged = {}

    for game in games:
        key = (
            normalize(game["title"]),
            game["date"].isoformat(),
        )

        if key not in merged:
            merged[key] = {
                **game,
                "sources": list(
                    game["sources"]
                ),
            }
            continue

        existing = merged[key]

        for source in game["sources"]:
            if source not in existing["sources"]:
                existing["sources"].append(
                    source
                )

        if len(game["platforms"]) > len(
            existing["platforms"]
        ):
            existing["platforms"] = (
                game["platforms"]
            )

        if (
            "store.steampowered.com"
            in game["url"]
        ):
            existing["url"] = game["url"]

        if (
            game["note"]
            and not existing["note"]
        ):
            existing["note"] = (
                game["note"]
            )

    return list(merged.values())


def select_premium(games, premium, limit):
    selected = []

    for game in games:
        title = game["title"]

        if is_excluded(title, premium):
            continue

        category = premium_category(
            title, premium
        )

        if not category:
            continue

        selected.append({
            **game,
            "category": category,
        })

    selected.sort(
        key=lambda game: (
            game["date"],
            game["title"].casefold(),
        )
    )

    return selected[:limit]


def main():
    print("=" * 42)
    print("ARTYKO GAME RELEASES V4 PREMIUM")
    print("=" * 42)

    print("Ora italiana:", NOW.isoformat())

    # V4 bloccata in simulazione.
    # Non contiene chiamate al webhook Discord.
    print("Modalita': SOLO SIMULAZIONE")

    premium = load_json(PREMIUM_FILE)
    config = load_json(SOURCES_FILE)

    days = int(
        config.get("days_ahead", 7)
    )
    limit = int(
        config.get("max_games", 10)
    )

    if not 1 <= days <= 31:
        raise ValueError(
            "days_ahead non valido."
        )

    if not 1 <= limit <= 10:
        raise ValueError(
            "max_games deve essere tra 1 e 10."
        )

    end_date = TODAY + timedelta(
        days=days - 1
    )

    print(
        "Periodo:",
        TODAY,
        "-",
        end_date,
    )

    games = []

    try:
        games.extend(
            fetch_gamesradar(
                config,
                TODAY,
                end_date,
            )
        )
    except (
        requests.RequestException,
        ValueError,
    ) as exc:
        print(
            "Errore GamesRadar:", exc
        )

    games.extend(
        fetch_steam(
            TODAY,
            end_date,
        )
    )

    merged = merge_games(games)

    print(
        "Uscite complessive:",
        len(merged)
    )

    selected = select_premium(
        merged,
        premium,
        limit,
    )

    print(
        "Grandi uscite selezionate:",
        len(selected)
    )

    print("\nANTEPRIMA CALENDARIO PREMIUM:")

    if not selected:
        print(
            "Nessuna grande uscita "
            "individuata nel periodo."
        )

    for game in selected:
        print("-" * 42)
        print(
            "Titolo:", game["title"]
        )
        print(
            "Data:", game["date"]
        )
        print(
            "Piattaforme:",
            game["platforms"]
        )
        print(
            "Categoria:",
            game["category"]
        )
        print(
            "Fonti:",
            " + ".join(game["sources"])
        )
        print(
            "URL:", game["url"]
        )
        print(
            "Verifica ufficiale:",
            "NON ESEGUITA"
        )

    print("\nSIMULAZIONE COMPLETATA.")
    print(
        "Nessun messaggio inviato su Discord."
    )


if __name__ == "__main__":
    main()
