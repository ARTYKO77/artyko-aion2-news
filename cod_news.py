
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

URL = "https://www.callofduty.com/blog"

print("ARTYKO COD NEWS - Diagnostica")

response = requests.get(
    URL,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
)
response.raise_for_status()

print("HTTP:", response.status_code)
print("HTML ricevuto:", len(response.content), "byte")

soup = BeautifulSoup(response.text, "html.parser")
articles = {}
pattern = re.compile(r"^/blog/20\d{2}/\d{2}/")

for link in soup.find_all("a", href=True):
    url = urljoin(URL, link["href"])
    parsed = urlparse(url)

    if parsed.netloc != "www.callofduty.com":
        continue

    if not pattern.match(parsed.path):
        continue

    title = link.get_text(" ", strip=True)

    if title:
        articles[url] = title

print("Articoli trovati:", len(articles))

for url, title in list(articles.items())[:5]:
    print("Titolo:", title[:150])
    print("URL:", url)
    print("---")

if not articles:
    print("Nessun link articolo nell'HTML.")
    print("Link totali:", len(soup.find_all("a", href=True)))
