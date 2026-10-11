
import requests
import re
import html
from urllib.parse import urljoin

APP_ID = 3932890

API_URL = (
    "https://api.steampowered.com/"
    "ISteamNews/GetNewsForApp/v2/"
)

print("ARTYKO TARKOV NEWS - TEST IMMAGINI", flush=True)

response = requests.get(
    API_URL,
    params={
        "appid": APP_ID,
        "count": 30,
        "maxlength": 0,
        "format": "json"
    },
    headers={
        "User-Agent": "ARTYKO-News-Bot/1.0"
    },
    timeout=25
)

print("HTTP API:", response.status_code, flush=True)
response.raise_for_status()

articles = response.json().get(
    "appnews", {}
).get("newsitems", [])

official = [
    item for item in articles
    if item.get("feed_type") == 1
    and item.get("feedlabel") == "Community Announcements"
]

print("ANNUNCI SELEZIONATI:", len(official), flush=True)

for article in official[:5]:
    print("\n" + "=" * 55)
    print("TITOLO:", article.get("title"))

    content = html.unescape(article.get("contents", ""))

    # Cerca immagini nei tag HTML e nel formato Steam BBCode.
    candidates = re.findall(
        r'\[img\](.*?)\[/img\]',
        content,
        flags=re.IGNORECASE | re.DOTALL
    )

    candidates += re.findall(
        r'<img[^>]+src=["\']([^"\']+)',
        content,
        flags=re.IGNORECASE
    )

    # Cerca anche URL diretti di immagini.
    candidates += re.findall(
        r'https?://[^\s\]<>"]+\.(?:jpg|jpeg|png|webp)'
        r'(?:\?[^\s\]<>"]*)?',
        content,
        flags=re.IGNORECASE
    )

    images = list(dict.fromkeys(
        urljoin("https://steamcommunity.com", url.strip())
        for url in candidates
        if url.strip()
    ))

    print("IMMAGINI TROVATE:", len(images))

    for image_url in images[:3]:
        print("URL IMMAGINE:", image_url)

        try:
            image_response = requests.get(
                image_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
                stream=True
            )

            print("HTTP IMMAGINE:", image_response.status_code)
            print(
                "TIPO IMMAGINE:",
                image_response.headers.get("Content-Type")
            )
            image_response.close()

        except requests.RequestException as error:
            print("ERRORE IMMAGINE:", error)

print("\nTEST COMPLETATO", flush=True)
