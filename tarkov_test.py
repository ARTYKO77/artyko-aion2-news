
import requests
import json

APP_ID = 3932890

URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

print("ARTYKO TARKOV NEWS - TEST STEAM", flush=True)

response = requests.get(
    URL,
    params={
        "appid": APP_ID,
        "count": 5,
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

for article in articles:
    print("\n-------------------")
    print("TITOLO:", article.get("title"))
    print("DATA:", article.get("date"))
    print("FONTE:", article.get("feedlabel"))
    print("URL:", article.get("url"))
    print("CONTENUTO:", article.get("contents", "")[:300])

if not articles:
    print("ATTENZIONE: Steam non ha restituito notizie.")
