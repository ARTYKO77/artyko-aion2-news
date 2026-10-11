
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests


# ============================================================
# ARTYKO | AION 2 EVENTS
# Calendario EU e promemoria Discord
# ============================================================

UTC = timezone.utc
SERVER_TZ = ZoneInfo("Europe/Berlin")

WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_AION2_EVENTS", ""
).strip()

DRY_RUN = (
    os.getenv("AION2_EVENTS_DRY_RUN", "true")
    .strip()
    .lower() != "false"
)

STATE_FILE = "aion2_events_state.json"
SOURCE_URL = "https://aion2.app/news/51"

CALENDAR_LIMIT = 12

# Avviso ideale: 5 minuti prima.
REMINDER_MINUTES = 5

# Recupero ritardi: fino a 20 minuti prima dell'evento.
# Se il controllo arriva tardi, inviamo comunque l'avviso
# prima dell'inizio, indicando il tempo reale rimanente.
REMINDER_LOOKAHEAD_MINUTES = 20


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

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        state = json.load(file)

    if not isinstance(state, dict):
        raise ValueError("Storico eventi non valido.")

    state.setdefault("calendar_message_id", None)
    state.setdefault("sent_reminders", [])

    if not isinstance(state["sent_reminders"], list):
        raise ValueError("Elenco promemoria non valido.")

    return state


def save_state(state):
    temporary_file = STATE_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(temporary_file, STATE_FILE)


def calculate_events(now):
    results = []
    seen = set()

    local_now = now.astimezone(SERVER_TZ)

    for day_offset in range(4):
        day = local_now.date() + timedelta(days=day_offset)

        for event_type in EVENTS:
            for minute_of_day in event_type["minutes"]:
                hour = minute_of_day // 60
                minute = minute_of_day % 60

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

                    start_utc = local_start.astimezone(UTC)

                    # Esclude gli orari inesistenti durante
                    # il passaggio all'ora legale.
                    roundtrip = start_utc.astimezone(SERVER_TZ)

                    if (
                        roundtrip.date() != day
                        or roundtrip.hour != hour
                        or roundtrip.minute != minute
                    ):
                        continue

                    if start_utc <= now:
                        continue

                    timestamp = int(start_utc.timestamp())

                    event_key = (
                        f"{event_type['id']}:{timestamp}"
                    )

                    if event_key in seen:
                        continue

                    seen.add(event_key)

                    results.append({
                        "id": event_type["id"],
                        "name": event_type["name"],
                        "icon": event_type["icon"],
                        "duration": event_type["duration"],
                        "start": start_utc,
                        "timestamp": timestamp,
                        "key": event_key,
                    })

    results.sort(
        key=lambda event: (
            event["start"],
            event["name"],
        )
    )

    return results


def build_calendar(events, now):
    lines = []

    for event in events[:CALENDAR_LIMIT]:
        timestamp = event["timestamp"]

        lines.append(
            f"**{event['icon']} {event['name']}**\n"
            f"🕒 <t:{timestamp}:F>\n"
            f"⏳ <t:{timestamp}:R> · "
            f"{event['duration']} min · "
            f"⌛ In programma"
        )

    description = "\n\n".join(lines)

    updated_at = now.astimezone(SERVER_TZ).strftime(
        "%H:%M"
    )

    return {
        "username": "ARTYKO AION 2 EVENTS",
        "allowed_mentions": {
            "parse": [],
        },
        "embeds": [
            {
                "title": (
                    "📅 ARTYKO | "
                    "CALENDARIO EVENTI AION 2"
                ),
                "description": description,
                "color": 0x00D8B4,
                "footer": {
                    "text": (
                        "Server EU · "
                        "Orario locale Discord · "
                        "Fonte calendario: AION2.APP · "
                        f"Aggiornato alle {updated_at}"
                    )
                },
            }
        ],
    }


def build_reminder(event, now):
    seconds_left = max(
        0,
        int((event["start"] - now).total_seconds())
    )

    minutes_left = max(
        1,
        (seconds_left + 59) // 60
    )

    if minutes_left <= REMINDER_MINUTES:
        notice = (
            f"**Mancano circa {minutes_left} minuti!**"
        )
    else:
        notice = (
            f"**Tra circa {minutes_left} minuti!**"
        )

    return {
        "username": "ARTYKO AION 2 EVENTS",
        "allowed_mentions": {
            "parse": [],
        },
        "embeds": [
            {
                "title": (
                    f"🔔 {event['icon']} "
                    f"{event['name']}"
                ),
                "description": (
                    f"{notice}\n\n"
                    f"🕒 Inizio: "
                    f"<t:{event['timestamp']}:F>\n"
                    f"⏳ Countdown: "
                    f"<t:{event['timestamp']}:R>\n"
                    f"⌛ Durata: "
                    f"{event['duration']} minuti\n\n"
                    "⚔️ **Preparati, ARTYKO!**"
                ),
                "color": 0x32FF87,
                "footer": {
                    "text": (
                        "ARTYKO | AION 2 EVENTS · "
                        "Server EU"
                    )
                },
            }
        ],
    }


def discord_request(method, url, payload):
    response = requests.request(
        method,
        url,
        json=payload,
        timeout=20,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Errore Discord HTTP "
            f"{response.status_code}: "
            f"{response.text[:300]}"
        )

    return response


def publish_calendar(payload, message_id):
    webhook = WEBHOOK_URL.rstrip("/")

    if message_id:
        edit_url = (
            f"{webhook}/messages/{message_id}"
        )

        response = requests.patch(
            edit_url,
            json=payload,
            timeout=20,
        )

        if response.status_code < 400:
            print(
                "Calendario Discord aggiornato."
            )
            return message_id

        if response.status_code != 404:
            raise RuntimeError(
                "Errore aggiornamento calendario: "
                f"HTTP {response.status_code} "
                f"{response.text[:300]}"
            )

        print(
            "Calendario precedente non trovato. "
            "Ne pubblico uno nuovo."
        )

    create_url = webhook + "?wait=true"

    response = discord_request(
        "POST",
        create_url,
        payload,
    )

    message = response.json()
    new_id = message.get("id")

    if not new_id:
        raise RuntimeError(
            "Discord non ha restituito "
            "l'ID del calendario."
        )

    print(
        "Nuovo calendario Discord pubblicato."
    )

    return new_id


def publish_reminder(event, now):
    payload = build_reminder(event, now)

    discord_request(
        "POST",
        WEBHOOK_URL,
        payload,
    )

    print(
        f"Promemoria inviato: "
        f"{event['name']} "
        f"({event['key']})"
    )


def find_due_reminders(events, now, sent):
    due = []

    for event in events:
        seconds_left = (
            event["start"] - now
        ).total_seconds()

        if event["key"] in sent:
            continue

        # Non inviare avvisi per eventi già iniziati.
        if seconds_left <= 0:
            continue

        # Finestra estesa per compensare
        # i ritardi di GitHub Actions.
        if seconds_left > (
            REMINDER_LOOKAHEAD_MINUTES * 60
        ):
            continue

        due.append(event)

    return due


def prune_reminders(state, now):
    cutoff = int(
        (now - timedelta(days=2)).timestamp()
    )

    kept = []

    for key in state["sent_reminders"]:
        try:
            timestamp = int(
                key.rsplit(":", 1)[1]
            )
        except (ValueError, IndexError):
            continue

        if timestamp >= cutoff:
            kept.append(key)

    state["sent_reminders"] = kept


def main():
    now = datetime.now(UTC)

    print("=" * 48)
    print("ARTYKO | AION 2 EVENTS")
    print("=" * 48)

    print("Server: EU")
    print("Fuso orario: Europe/Berlin")
    print(f"Modalita' sicura: {DRY_RUN}")
    print(
        f"Webhook configurato: "
        f"{bool(WEBHOOK_URL)}"
    )

    state = load_state()
    events = calculate_events(now)

    if not events:
        raise RuntimeError(
            "Nessun evento futuro trovato."
        )

    print("\nPROSSIMI EVENTI")
    print("-" * 48)

    for event in events[:CALENDAR_LIMIT]:
        local_start = event["start"].astimezone(
            SERVER_TZ
        )

        print(
            f"{local_start:%d/%m/%Y %H:%M} | "
            f"{event['icon']} "
            f"{event['name']} | "
            f"{event['duration']} min"
        )

    calendar = build_calendar(events, now)

    sent = set(state["sent_reminders"])

    due = find_due_reminders(
        events,
        now,
        sent,
    )

    print(
        "\nCalendario preparato: "
        "📅 ARTYKO | CALENDARIO EVENTI AION 2"
    )

    print(
        f"Promemoria da inviare: {len(due)}"
    )

    if DRY_RUN:
        print(
            "\nMODALITA' SICURA: "
            "nessun messaggio Discord inviato."
        )
        print("Storico non modificato.")
        print("Test completato.")
        return

    if not WEBHOOK_URL:
        raise RuntimeError(
            "Webhook Discord non configurato."
        )

    calendar_id = publish_calendar(
        calendar,
        state["calendar_message_id"],
    )

    if calendar_id != state["calendar_message_id"]:
        state["calendar_message_id"] = calendar_id
        save_state(state)

    for event in due:
        publish_reminder(event, now)

        state["sent_reminders"].append(
            event["key"]
        )

        save_state(state)

    prune_reminders(state, now)
    save_state(state)

    print("\nEsecuzione completata.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"\nERRORE: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
