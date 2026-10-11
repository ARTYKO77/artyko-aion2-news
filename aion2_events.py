
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests


# ============================================================
# ARTYKO | AION 2 EVENTS
# Calendario Discord + promemoria automatici
# ============================================================

UTC = timezone.utc
SERVER_TZ = ZoneInfo("Europe/Berlin")

WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_AION2_EVENTS", ""
).strip()

DRY_RUN = os.getenv(
    "AION2_EVENTS_DRY_RUN", "true"
).strip().lower() != "false"

STATE_FILE = "aion2_events_state.json"
SOURCE_URL = "https://aion2.app/news/51"

CALENDAR_LIMIT = 12
REMINDER_MINUTES = 5

# Le regole seguenti sono state ricavate dal calendario
# pubblico di AION2.APP e confrontate con il server EU.
# Potrebbero cambiare dopo aggiornamenti del gioco.
EVENTS = [
    {
        "id": "shugo",
        "name": "Shugo Festival",
        "icon": "🎪",
        "minutes": list(range(0, 1440, 60)),
        "duration": 3,
    },
    {
        "id": "invasion",
        "name": "Invasion Event",
        "icon": "⚔️",
        "minutes": list(range(30, 1440, 60)),
        "duration": 13,
    },
    {
        "id": "rift",
        "name": "Spacetime Rift",
        "icon": "🌀",
        "minutes": list(range(120, 1440, 180)),
        "duration": 10,
    },
]


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "calendar_message_id": None,
            "sent_reminders": [],
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Formato storico non valido")

        message_id = data.get("calendar_message_id")
        reminders = data.get("sent_reminders", [])

        if not isinstance(reminders, list):
            raise ValueError("Lista promemoria non valida")

        return {
            "calendar_message_id": message_id,
            "sent_reminders": reminders,
        }

    except (OSError, ValueError, TypeError) as error:
        raise RuntimeError(
            "Storico illeggibile: esecuzione interrotta "
            "per evitare duplicati."
        ) from error


def save_state(state):
    temporary = STATE_FILE + ".tmp"

    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(temporary, STATE_FILE)


def discord_time(value, style="F"):
    return f"<t:{int(value.timestamp())}:{style}>"


def event_key(event):
    return (
        f"{event['id']}:"
        f"{int(event['start'].timestamp())}"
    )


def calculate_events(now):
    result = []
    today = now.astimezone(SERVER_TZ).date()

    for offset in range(3):
        day = today + timedelta(days=offset)

        for event in EVENTS:
            for minute_of_day in event["minutes"]:
                hour, minute = divmod(minute_of_day, 60)

                # Gestione dei cambi tra ora legale e solare.
                for fold in (0, 1):
                    local_start = datetime(
                        day.year,
                        day.month,
                        day.day,
                        hour,
                        minute,
                        tzinfo=SERVER_TZ,
                        fold=fold,
                    )

                    start = local_start.astimezone(UTC)
                    roundtrip = start.astimezone(SERVER_TZ)

                    if (
                        roundtrip.replace(tzinfo=None)
                        != local_start.replace(tzinfo=None)
                    ):
                        continue

                    # Non duplicare orari non ambigui.
                    if fold == 1:
                        first_start = local_start.replace(
                            fold=0
                        ).astimezone(UTC)

                        if first_start == start:
                            continue

                    end = start + timedelta(
                        minutes=event["duration"]
                    )

                    if end <= now:
                        continue

                    result.append({
                        "id": event["id"],
                        "name": event["name"],
                        "icon": event["icon"],
                        "start": start,
                        "end": end,
                        "duration": event["duration"],
                    })

    result.sort(
        key=lambda event: (
            event["start"],
            event["id"],
        )
    )

    return result


def build_calendar(events, now):
    lines = []

    for event in events[:CALENDAR_LIMIT]:
        active = event["start"] <= now < event["end"]

        status = (
            "🟢 IN CORSO"
            if active
            else "⏳ In programma"
        )

        lines.append(
            f"{event['icon']} **{event['name']}**\n"
            f"🕒 {discord_time(event['start'], 'F')}\n"
            f"⏳ {discord_time(event['start'], 'R')}"
            f" · {event['duration']} min"
            f" · {status}"
        )

    return {
        "username": "ARTYKO AION 2 EVENTS",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": (
                    "📅 ARTYKO | CALENDARIO EVENTI AION 2"
                ),
                "description": (
                    "\n\n".join(lines)
                    if lines
                    else "Nessun evento disponibile."
                ),
                "color": 0x00D9C0,
                "footer": {
                    "text": (
                        "Server EU · Orario locale Discord · "
                        "Fonte calendario: AION2.APP"
                    )
                },
                "timestamp": now.isoformat(),
            }
        ],
    }


def build_reminder(event):
    return {
        "username": "ARTYKO AION 2 EVENTS",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": (
                    f"🔔 {event['icon']} "
                    f"{event['name']}"
                ),
                "description": (
                    "**L'evento sta per iniziare!**\n\n"
                    f"🕒 {discord_time(event['start'], 'F')}\n"
                    f"⏳ {discord_time(event['start'], 'R')}\n"
                    f"⏱️ Durata: {event['duration']} minuti\n"
                    "🌍 Server: **EU**"
                ),
                "color": 0x39FF14,
                "footer": {
                    "text": (
                        "ARTYKO | AION 2 EVENT REMINDER"
                    )
                },
            }
        ],
    }


def discord_request(method, url, payload=None):
    try:
        response = requests.request(
            method,
            url,
            json=payload,
            timeout=20,
            headers={
                "User-Agent": "ARTYKO-AION2-Events/1.0"
            },
        )

        # Discord può applicare limiti temporanei.
        if response.status_code == 429:
            raise RuntimeError(
                "Discord rate limit: riprovare più tardi."
            )

        response.raise_for_status()
        return response

    except requests.RequestException as error:
        raise RuntimeError(
            f"Richiesta Discord fallita: {error}"
        ) from error


def publish_calendar(payload, message_id):
    if message_id:
        url = (
            WEBHOOK_URL.rstrip("/")
            + f"/messages/{message_id}"
        )

        response = requests.patch(
            url,
            json=payload,
            timeout=20,
        )

        if response.status_code == 404:
            print(
                "Calendario precedente non trovato. "
                "Ne verra' creato uno nuovo."
            )
        else:
            response.raise_for_status()
            print("Calendario Discord aggiornato.")
            return message_id

    separator = "&" if "?" in WEBHOOK_URL else "?"
    url = WEBHOOK_URL + separator + "wait=true"

    response = discord_request(
        "POST",
        url,
        payload,
    )

    data = response.json()
    new_id = data.get("id")

    if not new_id:
        raise RuntimeError(
            "Discord non ha restituito l'ID del calendario."
        )

    print("Nuovo calendario Discord pubblicato.")
    return new_id


def publish_reminder(event):
    payload = build_reminder(event)

    discord_request(
        "POST",
        WEBHOOK_URL,
        payload,
    )

    print(
        "Promemoria inviato:",
        event["name"],
        event["start"].isoformat(),
    )


def find_due_reminders(events, now, sent):
    due = []

    for event in events:
        seconds_until = (
            event["start"] - now
        ).total_seconds()

        # Avviso nei 5 minuti prima dell'evento.
        # Non inviare se manca meno di 1 minuto.
        if not (
            60 <= seconds_until <= REMINDER_MINUTES * 60
        ):
            continue

        if event_key(event) not in sent:
            due.append(event)

    return due


def main():
    now = datetime.now(UTC)
    state = load_state()
    events = calculate_events(now)

    print("=" * 55)
    print("ARTYKO | AION 2 EVENTS")
    print("=" * 55)
    print("Server: EU")
    print("Fuso orario: Europe/Berlin")
    print("Modalita' sicura:", DRY_RUN)
    print("Webhook configurato:", bool(WEBHOOK_URL))
    print()

    print("PROSSIMI EVENTI")
    print("-" * 55)

    for event in events[:CALENDAR_LIMIT]:
        local = event["start"].astimezone(SERVER_TZ)

        print(
            f"{local:%d/%m/%Y %H:%M} | "
            f"{event['icon']} {event['name']} | "
            f"{event['duration']} min"
        )

    print()

    payload = build_calendar(events, now)

    print(
        "Calendario preparato:",
        payload["embeds"][0]["title"],
    )

    sent = set(state["sent_reminders"])

    # Manteniamo solo i promemoria recenti.
    cutoff = int(
        (now - timedelta(days=2)).timestamp()
    )

    sent = {
        key for key in sent
        if (
            key.rsplit(":", 1)[-1].isdigit()
            and int(key.rsplit(":", 1)[-1]) >= cutoff
        )
    }

    due = find_due_reminders(events, now, sent)

    print("Promemoria da inviare:", len(due))

    for event in due:
        print(
            event["icon"],
            event["name"],
            event["start"].isoformat(),
        )

    if DRY_RUN:
        print()
        print(
            "MODALITA' SICURA: "
            "nessun messaggio Discord inviato."
        )
        print("Storico non modificato.")
        print("Test completato.")
        return

    if not WEBHOOK_URL:
        raise RuntimeError(
            "Secret DISCORD_WEBHOOK_AION2_EVENTS mancante."
        )

    # Pubblica o aggiorna il calendario.
    previous_id = state["calendar_message_id"]

    new_id = publish_calendar(
        payload,
        previous_id,
    )

    state["calendar_message_id"] = new_id

    # Salviamo subito l'ID per evitare calendari doppi.
    if new_id != previous_id:
        state["sent_reminders"] = sorted(sent)
        save_state(state)

    # Invia i promemoria uno alla volta.
    for event in due:
        publish_reminder(event)

        sent.add(event_key(event))
        state["sent_reminders"] = sorted(sent)
        save_state(state)

    # Aggiorna lo storico anche se non ci sono avvisi.
    state["sent_reminders"] = sorted(sent)
    save_state(state)

    print()
    print("Esecuzione completata.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"ERRORE: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
