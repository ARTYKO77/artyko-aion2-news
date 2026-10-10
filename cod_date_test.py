
import json
import re
import requests
from bs4 import BeautifulSoup

URLS = [
    "https://www.callofduty.com/blog/2026/10/call-of-duty-modern-warfare-4-dmz-how-to-play-forward-operating-base-guide",
    "https://www.callofduty.com/blog/2026/10/call-of-duty-modern-warfare-4-dmz-deep-dive-hajin",
    "https://www.callofduty.com/blog/2026/05/call-of-duty-modern-warfare-4-preorder-benefits-game-editions-details",
]

for url in URLS:
    print("\nARTICOLO:", url)

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name") or ""
        if any(word in key.lower() for word in
               ("date", "published", "modified", "time")):
            print("META:", key, tag.get("content"))

    for script in soup.find_all(
        "script", type="application/ld+json"
    ):
        try:
            data = json.loads(script.get_text())
            print("JSON-LD:", str(data)[:1200])
        except json.JSONDecodeError:
            pass

    dates = re.findall(
        r'20\d{2}-\d{2}-\d{2}(?:T[\d:.+-Z]+)?',
        response.text
    )
    print("DATE ISO TROVATE:", list(dict.fromkeys(dates))[:10])
