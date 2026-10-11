
import json
import re
import requests
from bs4 import BeautifulSoup

with open("releases_sources.json", encoding="utf-8") as f:
    config = json.load(f)

source = next(
    (
        s for s in config["editorial_sources"]
        if s["name"] == "GamesRadar" and s["enabled"]
    ),
    None,
)

if not source:
    raise RuntimeError("GamesRadar non attiva nel file JSON.")

response = requests.get(
    source["url"],
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30,
)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

print("ARTYKO - ANALISI STRUTTURA GAMESRADAR")
print("HTTP:", response.status_code)

months = (
    "January", "February", "March", "April",
    "May", "June", "July", "August",
    "September", "October", "November", "December"
)

date_pattern = re.compile(
    r"\b(?:" + "|".join(months) +
    r")\s+\d{1,2}(?:,\s*20\d{2})?\b",
    re.IGNORECASE,
)

headings = soup.select("h2, h3")

for heading in headings:
    title = heading.get_text(" ", strip=True)

    if "OCTOBER 2026" not in title.upper() \
       and "NOVEMBER 2026" not in title.upper():
        continue

    print("\nSEZIONE:", title)

    sibling = heading.find_next_sibling()
    inspected = 0

    while sibling and inspected < 12:
        if sibling.name in ("h2", "h3"):
            break

        text = sibling.get_text(" ", strip=True)

        if text:
            print(
                "TAG:", sibling.name,
                "| TESTO:", text[:350]
            )
            print(
                "DATE:", date_pattern.findall(text)[:8]
            )
            inspected += 1

        sibling = sibling.find_next_sibling()

print("\nANALISI COMPLETATA.")
print("Nessun messaggio inviato su Discord.")
