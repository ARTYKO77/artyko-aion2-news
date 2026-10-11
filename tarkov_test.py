
import requests
from bs4 import BeautifulSoup

URL = "https://www.escapefromtarkov.com/news"

print("ARTYKO TARKOV NEWS - TEST FONTE", flush=True)

try:
    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20
    )

    print("HTTP STATUS:", response.status_code)
    print("URL FINALE:", response.url)
    print("DIMENSIONE PAGINA:", len(response.content))

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    print("TITOLO PAGINA:",
          soup.title.get_text(strip=True)
          if soup.title else "Non trovato")

    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(" ", strip=True)

        if title and href:
            links.append((title, href))

    print("LINK TROVATI:", len(links))

    for title, href in links[:20]:
        print("LINK:", title[:100], "|", href)

except Exception as error:
    print("ERRORE:", str(error))
    raise
