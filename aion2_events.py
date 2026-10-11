
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests


# ============================================================
# ARTYKO | AION 2 EVENTS
# Dashboard Discord: calendario + prossimo evento
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
            "next_event_message_id": None,
            "sent_reminders": [],
            "old_reminder_message_ids": [],
        }

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        state = json.load(file)

    if not isinstance(state, dict):
        raise ValueError("Storico eventi non valido.")

    state.setdefault("calendar_message_id", None)
    state.setdefault("next_event_message_id", None)
    state.setdefault("sent_reminders", [])
    state.setdefault("old_reminder_message_ids", [])

    if not isinstance(state["sent_reminders"], list):
        raise ValueError("Elenco promemoria non valido.")

    if not isinstance(
        state["old_reminder_message_ids"], list
    ):
        raise ValueError(
            "Elenco messaggi da eliminare non valido."
        )

    return state


def save_state(state):
    temporary_file = STATE_FILE + ".tmp"

    with open(
        temporary_file, "w", encoding="utf-8"
    ) as file:
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
        day = (
            local_now.date()
            + timedelta(days=day_offset)
        )

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
                    roundtrip = start_utc.astimezone(
                        SERVER_TZ
                    )

                    if (
                        roundtrip.date() != day
                        or roundtrip.hour != hour
                        or roundtrip.minute != minute
                    ):
                        continue

                    if start_utc <= now:
                        continue

                    timestamp = int(
                        start_utc.timestamp()
                    )

                    key = (
                        f"{event_type['id']}:{timestamp}"
                    )

                    if key in seen:
                        continue

                    seen.add(key)

                    results.append({
                        "id": event_type["id"],
                        "name": event_type["name"],
                        "icon": event_type["icon"],
                        "duration": event_type["duration"],
                        "start": start_utc,
                        "timestamp": timestamp,
                        "key": key,
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
            "⌛ In programma"
        )

    updated_at = now.astimezone(
        SERVER_TZ
    ).strftime("%H:%M")

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
                "description": "\n\n".join(lines),
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


def build_next_event(events, now):
    if not events:
        raise RuntimeError(
            "Nessun evento futuro disponibile."
        )

    next_start = events[0]["start"]

    simultaneous = [
        event
        for event in events
        if event["start"] == next_start
    ]

    timestamp = simultaneous[0]["timestamp"]

    seconds_left = max(
        0,
        int((next_start - now).total_seconds())
    )

    minutes_left = (
        seconds_left + 59
    ) // 60

    if minutes_left <= 5:
        status = "🚨 **EVENTO IMMINENTE!**"
        color = 0x32FF87
    elif minutes_left <= 20:
        status = "🔔 **PREPARATI, ARTYKO!**"
        color = 0x00D8B4
    else:
        status = "📡 **PROSSIMO EVENTO**"
        color = 0x00B8FF

    event_lines = []

    for event in simultaneous:
        event_lines.append(
            f"**{event['icon']} {event['name']}**\n"
            f"⌛ Durata: {event['duration']} minuti"
        )

    description = (
        f"{status}\n\n"
        + "\n\n".join(event_lines)
        + "\n\n"
        + f"🕒 Inizio: <t:{timestamp}:F>\n"
        + f"⏳ Countdown: <t:{timestamp}:R>\n"
        + "🌍 Server: EU\n\n"
        + "⚔️ **Preparati, ARTYKO!**"
    )

    return {
        "username": "ARTYKO AION 2 EVENTS",
        "allowed_mentions": {
            "parse": [],
        },
        "embeds": [
            {
                "title": (
                    "🔔 ARTYKO | PROSSIMO EVENTO"
                ),
                "description": description,
                "color": color,
                "footer": {
                    "text": (
                        "ARTYKO | AION 2 EVENTS · "
                        "Aggiornamento automatico"
                    )
                },
            }
        ],
    }


def discord_request(method, url, payload=None):
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


def publish_or_update(payload, message_id, label):
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
            print(f"{label} aggiornato.")
            return message_id

        if response.status_code != 404:
            raise RuntimeError(
                f"Errore aggiornamento {label}: "
                f"HTTP {response.status_code} "
                f"{response.text[:300]}"
            )

        print(
            f"{label} precedente non trovato. "
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
            f"Discord non ha restituito "
            f"l'ID per {label}."
        )

    print(f"{label} pubblicato.")

    return new_id


def cleanup_known_old_reminders(state):
    """
    Elimina solo gli eventuali messaggi
    esplicitamente registrati nello storico.

    I promemoria della versione precedente
    non salvavano i loro ID, quindi non possono
    essere individuati automaticamente.
    """

    message_ids = list(
        state["old_reminder_message_ids"]
    )

    if not message_ids:
        print(
            "Nessun vecchio promemoria "
            "registrato da eliminare."
        )
        return

    webhook = WEBHOOK_URL.rstrip("/")

    for message_id in message_ids:
        url = (
            f"{webhook}/messages/{message_id}"
        )

        response = requests.delete(
            url,
            timeout=20,
        )

        if response.status_code in (200, 204, 404):
            state["old_reminder_message_ids"].remove(
                message_id
            )
            save_state(state)
            print(
                "Vecchio promemoria eliminato: "
                f"{message_id}"
            )
        else:
            raise RuntimeError(
                "Errore eliminazione promemoria: "
                f"HTTP {response.status_code}"
            )


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

    calendar_payload = build_calendar(
        events, now
    )

    next_event_payload = build_next_event(
        events, now
    )

    print(
        "\nDashboard preparata:"
    )
    print(
        "1. 📅 Calendario eventi"
    )
    print(
        "2. 🔔 Prossimo evento"
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

    calendar_id = publish_or_update(
        calendar_payload,
        state["calendar_message_id"],
        "Calendario Discord",
    )

    if calendar_id != state["calendar_message_id"]:
        state["calendar_message_id"] = calendar_id
        save_state(state)

    next_event_id = publish_or_update(
        next_event_payload,
        state["next_event_message_id"],
        "Pannello prossimo evento",
    )

    if next_event_id != state["next_event_message_id"]:
        state["next_event_message_id"] = next_event_id
        save_state(state)

    cleanup_known_old_reminders(state)

    print(
        "\nDashboard aggiornata correttamente."
    )
    print(
        "Nessun nuovo promemoria separato inviato."
    )
    print("Esecuzione completata.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"\nERRORE: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
