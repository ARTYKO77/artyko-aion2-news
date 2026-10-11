
import json
import os
import sys
from pathlib import Path

import requests


# ==========================================================
# ARTYKO SEA OF THIEVES - TEST DISCORD
# Un solo messaggio di prova, senza modificare lo storico.
# ==========================================================

WEBHOOK = os.getenv(
    "DISCORD_WEBHOOK_SEAOFTHIEVES", ""
).strip()

COVER = Path("seaofthieves_cover.png")

# Sicurezza: non invia nulla se non autorizzato.
SEND_TEST = os.getenv(
    "SEAOFTHIEVES_SEND_TEST", "false"
).lower() == "true"


def main():
    print("ARTYKO SEA OF THIEVES - TEST DISCORD")

    if not WEBHOOK:
        raise RuntimeError(
            "Webhook Sea of Thieves non configurato."
        )

    if not COVER.is_file():
        raise FileNotFoundError(
            "Copertina seaofthieves_cover.png non trovata."
        )

    print("Webhook configurato: SI")
    print("Copertina trovata: SI")
    print(f"Dimensione copertina: {COVER.stat().st_size} byte")

    if not SEND_TEST:
        print("MODALITA' SICURA: nessun messaggio inviato.")
        print("Test preliminare completato.")
        return

    payload = {
        "username": "ARTYKO SEA OF THIEVES NEWS",
        "content": "🏴‍☠️ **ARTYKO | TEST NOTIZIE SEA OF THIEVES**",
        "embeds": [
            {
                "title": "☠️ La ciurma ARTYKO è pronta a salpare!",
                "description": (
                    "Questo è un messaggio di collaudo "
                    "del nostro bot Sea of Thieves.\n\n"
                    "✅ Webhook funzionante\n"
                    "✅ Copertina ARTYKO collegata\n"
                    "✅ Canale Discord configurato\n\n"
                    "Le prossime notizie saranno recuperate "
                    "automaticamente dagli annunci di Steam.\n\n"
                    "**ARRRRR!** 🏴‍☠️"
                ),
                "color": 0x21D8C3,
                "image": {
                    "url": "attachment://seaofthieves_cover.png"
                },
                "footer": {
                    "text": "ARTYKO • Sea of Thieves News"
                },
            }
        ],
        "allowed_mentions": {
            "parse": []
        },
    }

    with COVER.open("rb") as image:
        response = requests.post(
            WEBHOOK,
            data={
                "payload_json": json.dumps(
                    payload,
                    ensure_ascii=False
                )
            },
            files={
                "files[0]": (
                    "seaofthieves_cover.png",
                    image,
                    "image/png"
                )
            },
            timeout=45,
        )

    if response.status_code not in (200, 204):
        print(
            f"Errore Discord: HTTP {response.status_code}"
        )
        response.raise_for_status()
        raise RuntimeError(
            "Risposta Discord inattesa."
        )

    print("SUCCESSO: messaggio di test inviato su Discord!")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"ERRORE: {type(error).__name__}: {error}",
            file=sys.stderr
        )
        sys.exit(1)
