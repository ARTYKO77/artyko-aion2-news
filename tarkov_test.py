
import requests
from datetime import datetime, timezone

APP_ID = 3932890

URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

print("ARTYKO TARKOV NEWS - TEST FONTI STEAM", flush=True)

response = requests.get(
    URL,
    params={
        "appid": APP_ID,
        "count": 20,
        "maxlength": 500,
        "format": "json"
    },
    headers={
        "User-Agent": "ARTYKO-News-Bot/1.0"
    },
    timeout=20
)

print("HTTP STATUS:", response.status_code, flush=True)
response.raise_for_status()

data = response.json()
articles = data.get("appnews", {}).get("newsitems", [])

print("NOTIZIE TROVATE:", len(articles), flush=True)

for index, article in enumerate(articles, 1):
    print("\n" + "=" * 55)
    print("NOTIZIA:", index)

    print("TITOLO:", article.get("title"))
    print("FONTE:", article.get("feedlabel"))
    print("FEED TYPE:", article.get("feed_type"))
    print("APP ID:", article.get("appid"))
    print("AUTORE:", article.get("author"))

    timestamp = article.get("date")

    if timestamp:
        date = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc
        )
        print("DATA UTC:", date.isoformat())

    print("URL:", article.get("url"))
    print("GID:", article.get("gid"))
    print("CONTENUTO:", article.get("contents", "")[:300])

print("\n" + "=" * 55)
print("TEST COMPLETATO", flush=True)

if not articles:
    print("ATTENZIONE: nessuna notizia restituita.")
