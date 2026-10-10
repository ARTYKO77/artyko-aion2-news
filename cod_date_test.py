
import json
import requests
from bs4 import BeautifulSoup

URL = "https://www.callofduty.com/blog/2026/10/call-of-duty-modern-warfare-4-dmz-deep-dive-hajin"

response = requests.get(
    URL,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
)
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

        if item.get("@type") == "BlogPosting":
            print("TITOLO:", item.get("headline"))
            print("DATA:", item.get("datePublished"))
            print("IMMAGINE:", item.get("image"))
            print("DESCRIZIONE:", item.get("description"))

print("TEST HAJIN COMPLETATO")
