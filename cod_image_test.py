
from cod_news import get_articles, send_discord

print("Recupero una notizia per il test...", flush=True)

articles, errors = get_articles()

if not articles or errors:
    raise RuntimeError("Impossibile completare il test")

article = articles[0].copy()
article["title"] = "🧪 TEST IMMAGINE | " + article["title"]

print("Invio messaggio di prova...", flush=True)
send_discord(article)

print("TEST COMPLETATO", flush=True)
