
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# ========================================
# ARTYKO GAME RELEASES - PARSER V3
# SOLO TEST - NESSUNA PUBBLICAZIONE
# ========================================

CONFIG_FILE = "releases_sources.json"
TZ = ZoneInfo("Europe/Rome")

TODAY = datetime.now(TZ).date()
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

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
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


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as file:
        return json.load(file)


def get_source(config):
    for source in config.get("editorial_sources", []):
        if (
            source.get("name") == "GamesRadar"
            and source.get("enabled")
        ):
            return source

    raise RuntimeError("GamesRadar non abilitata.")


def parse_entry(text, section_year):
    match = ENTRY_PATTERN.match(text.strip())

    if not match:
        return None

    info, month_name, day, explicit_year, note = match.groups()
    month_number = MONTHS.get(month_name.upper())

    if not month_number:
        return None

    year = int(explicit_year or section_year)

    try:
        release_date = datetime(
            year, month_number, int(day)
        ).date()
    except ValueError:
        return None

    platform_match = PLATFORM_PATTERN.match(info.strip())

    if platform_match:
        title = platform_match.group(1).strip()
        platforms = platform_match.group(2).strip()
    else:
        title = info.strip()
        platforms = "Non specificate"

    if not title:
        return None

    return {
        "title": title,
        "platforms": platforms,
        "date": release_date,
        "note": note or "",
        "source": "GamesRadar",
        "verified_officially": False,
    }


def main():
    config = load_config()
    source = get_source(config)

    days = int(config.get("days_ahead", 7))
    if not 1 <= days <= 31:
        raise ValueError("days_ahead deve essere tra 1 e 31.")

    end_date = TODAY + timedelta(days=days - 1)

    print("===================================")
    print("ARTYKO GAMESRADAR PARSER V3")
    print("===================================")
    print("Oggi:", TODAY)
    print("Periodo:", TODAY, "-", end_date)
    print("Fonte:", source["url"])

    response = requests.get(
        source["url"],
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    found = {}
    rejected = []

    for heading in soup.select("h2, h3"):
        heading_text = heading.get_text(
            " ", strip=True
        ).upper()

        if not (
            "GAMES OF" in heading_text
            or "NEW GAMES OF" in heading_text
        ):
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

        section_year = int(year_match.group())
        section_month = MONTHS[month_name]

        # Analizza solo i mesi nel periodo scelto.
        section_month_index = section_year * 12 + section_month
        first_index = TODAY.year * 12 + TODAY.month
        last_index = end_date.year * 12 + end_date.month

        if not first_index <= section_month_index <= last_index:
            continue

        sibling = heading.find_next_sibling()

        while sibling and sibling.name not in ("h2", "h3"):
            if sibling.name in ("ul", "ol"):
                for li in sibling.find_all(
                    "li", recursive=False
                ):
                    text = li.get_text(" ", strip=True)
                    game = parse_entry(text, section_year)

                    if game is None:
                        rejected.append(text)
                        continue

                    if not TODAY <= game["date"] <= end_date:
                        continue

                    key = (
                        game["title"].casefold(),
                        game["date"].isoformat(),
                        game["platforms"].casefold(),
                    )

                    found[key] = game

            sibling = sibling.find_next_sibling()

    games = sorted(
        found.values(),
        key=lambda game: (
            game["date"],
            game["title"].casefold(),
        ),
    )

    print("\nUSCITE NEI PROSSIMI 7 GIORNI:")
    print("-----------------------------------")

    for game in games:
        note = (
            f" [{game['note']}]"
            if game["note"] else ""
        )

        print(
            f"{game['date']} | "
            f"{game['title']} | "
            f"{game['platforms']}{note}"
        )

    print("\nTOTALE USCITE:", len(games))

    if rejected:
        print("\nVOCI NON RICONOSCIUTE:")
        for item in rejected[:15]:
            print("-", item[:180])

    print("\nVERIFICA DATE:")
    print(
        "Le date provengono da GamesRadar."
    )
    print(
        "NON sono ancora confermate da fonti ufficiali."
    )

    print("\nTEST COMPLETATO.")
    print("Nessun messaggio inviato su Discord.")


if __name__ == "__main__":
    main()
