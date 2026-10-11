
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

with open("releases_sources.json", encoding="utf-8") as file:
    config = json.load(file)

source = next(
    (
        item for item in config["editorial_sources"]
        if item["name"] == "GamesRadar" and item["enabled"]
    ),
    None,
)

if not source:
    raise RuntimeError("GamesRadar non attiva.")

response = requests.get(
    source["url"],
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30,
)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

now = datetime.now(ZoneInfo("Europe/Rome"))
year = now.year

months = {
    "JANUARY": 1, "FEBRUARY": 2,
    "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10,
    "NOVEMBER": 11, "DECEMBER": 12,
}

print("ARTYKO - ESTRAZIONE GAMESRADAR V2")
print("Data italiana:", now.date())
print()

total = 0

for heading in soup.select("h2, h3"):
    heading_text = heading.get_text(" ", strip=True).upper()

    month_name = next(
        (name for name in months if name in heading_text),
        None,
    )

    year_match = re.search(r"\b20\d{2}\b", heading_text)

    if not month_name or not year_match:
        continue

    section_year = int(year_match.group())
    section_month = months[month_name]

    # Analizziamo soltanto il mese corrente e quello successivo.
    month_difference = (
        (section_year - year) * 12
        + section_month - now.month
    )

    if month_difference not in (0, 1):
        continue

    print(f"SEZIONE: {heading_text}")

    sibling = heading.find_next_sibling()

    while sibling and sibling.name not in ("h2", "h3"):
        if sibling.name in ("ul", "ol"):
            for li in sibling.find_all("li", recursive=False):
                text = li.get_text(" ", strip=True)

                # Esempio:
                # Nome Gioco (PC, PS5) - October 15
                match = re.match(
                    r"^(.+?)\s*[\-–—]\s*"
                    r"([A-Za-z]+)\s+(\d{1,2})"
                    r"(?:,\s*(20\d{2}))?\s*$",
                    text,
                )

                if not match:
                    print("NON RICONOSCIUTO:", text[:150])
                    continue

                game_info = match.group(1).strip()
                date_month = match.group(2).upper()
                day = int(match.group(3))
                release_year = int(match.group(4) or section_year)

                if date_month not in months:
                    continue

                try:
                    release_date = datetime(
                        release_year,
                        months[date_month],
                        day,
                    ).date()
                except ValueError:
                    continue

                platform_match = re.match(
                    r"^(.*?)\s*\(([^()]*)\)$",
                    game_info,
                )

                if platform_match:
                    title = platform_match.group(1).strip()
                    platforms = platform_match.group(2).strip()
                else:
                    title = game_info
                    platforms = "Non specificate"

                print(
                    f"OK | {title} | "
                    f"{platforms} | {release_date}"
                )

                total += 1

        sibling = sibling.find_next_sibling()

print()
print("TOTALE GIOCHI ESTRATTI:", total)
print("Nessun messaggio inviato su Discord.")
