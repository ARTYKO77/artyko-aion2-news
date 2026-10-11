
import json
import re
import requests
from bs4 import BeautifulSoup

CONFIG_FILE = "releases_sources.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def main():
    with open(CONFIG_FILE, encoding="utf-8") as file:
        config = json.load(file)

    print("======================================")
    print("ARTYKO - TEST FONTI GAME RELEASES")
    print("======================================")

    for source in config["editorial_sources"]:
        if not source.get("enabled", False):
            continue

        print(f"\nFONTE: {source['name']}")
        print(f"URL: {source['url']}")

        try:
            response = requests.get(
                source["url"],
                headers=HEADERS,
                timeout=25,
            )

            print(f"HTTP: {response.status_code}")
            print(f"URL finale: {response.url}")
            print(f"Dimensione HTML: {len(response.content)} byte")

            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()

            headings = [
                element.get_text(" ", strip=True)
                for element in soup.select("h1, h2, h3")
            ]

            print("Prime intestazioni trovate:")

            for heading in headings[:12]:
                print(f" - {heading[:140]}")

            text = soup.get_text(" ", strip=True)

            dates = re.findall(
                r"\b(?:January|February|March|April|May|June|"
                r"July|August|September|October|November|December)"
                r"\s+\d{1,2}(?:,\s*20\d{2})?\b",
                text,
                flags=re.IGNORECASE,
            )

            print(f"Date testuali individuate: {len(dates)}")
            print(f"Esempi: {dates[:8]}")

            if not headings and not dates:
                print("ATTENZIONE: contenuto non riconosciuto.")
            else:
                print("Pagina leggibile: analisi preliminare riuscita.")

        except requests.RequestException as error:
            print(f"ERRORE: {error}")

    print("\nTEST TERMINATO.")
    print("Nessun messaggio inviato su Discord.")

if __name__ == "__main__":
    main()
