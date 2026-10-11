
from tarkov_news import get_articles, send_discord, COVER

print("ARTYKO TARKOV - TEST COPERTINA", flush=True)

if not COVER.is_file():
    raise RuntimeError(
        "Copertina tarkov_cover.png non trovata!"
    )

print("Copertina trovata:", COVER.name, flush=True)

articles = get_articles()

if not articles:
    raise RuntimeError("Nessuna notizia disponibile")

article = articles[-1].copy()
article["title"] = "🧪 TEST COPERTINA | " + article["title"]

print("Invio messaggio di prova...", flush=True)

send_discord(article)

print("TEST COMPLETATO", flush=True)
