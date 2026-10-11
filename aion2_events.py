
import os
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests


# ============================================================
# ARTYKO | AION 2 EVENTS
# Calendario automatico + notifiche Discord
# ============================================================

SERVER_TIMEZONE = ZoneInfo("Europe/Berlin")
UTC = timezone.utc

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_AION2_EVENTS", "").strip()

# Modalità sicura predefinita: nessun invio a Discord.
DRY_RUN = os.getenv("AION2_EVENTS_DRY_RUN", "true").lower() != "false"

HISTORY_FILE = "aion2_events_state.json"

SOURCE_URL = "https://aion2.app/news/51"

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

REMINDER_MINUTES = 5
CALENDAR_LIMIT = 12

# Margine per eventuali ritardi nell'esecuzione GitHub Actions.
# Un avviso viene considerato soltanto se mancano ancora
# almeno 60 secondi all'inizio dell'evento.
REMINDER_WINDOW_SECONDS = 300


def load_state():
    if not os.path.exists(HISTORY_FILE):
        return {
            "calendar_message_id": None,
            "sent_reminders": [],
        }

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)

        return {
            "calendar_message_id": state.get("calendar_message_id"),
            "sent_reminders": state.get("sent_reminders", []),
        }

    except (OSError, ValueError, TypeError):
        raise RuntimeError(
            "Impossibile leggere lo storico degli eventi. "
            "Esecuzione interrotta per evitare duplicati."
        )


def save_state(state):
    temp_file = HISTORY_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2, ensure_ascii=False)

    os.replace(temp_file, HISTORY_FILE)


def discord_timestamp(date, style="F"):
    return f"<t:{int(date.timestamp())}:{style}>"


def calculate_events(now):
    results = []

    local_today = now.astimezone(SERVER_TIMEZONE).date()

    for day_offset in range(3):
        day = local_today + timedelta(days=day_offset)

        for event in EVENTS:
            for minute_of_day in event["minutes"]:
                hour, minute = divmod(minute_of_day, 60)

                local_start = datetime(
                    day.year,
                    day.month,
                    day.day,
                    hour,
                    minute,
                    tzinfo=SERVER_TIMEZONE,
                )

                start = local_start.astimezone(UTC)

                # Evita orari locali inesistenti nel cambio ora.
                if start.astimezone(SERVER_TIMEZONE).replace(
                    tzinfo=None
                ) != local_start.replace(tzinfo=None):
                    continue

                end = start + timedelta(minutes=event["duration"])

                if end <= now:
                    continue

                results.append({
                    "id": event["id"],
                    "name": event["name"],
                    "icon": event["icon"],
                    "start": start,
                    "end": end,
                    "duration": event["duration"],
                })

    results.sort(key=lambda item: (item["start"], item["id"]))

    return results


def build_calendar(events, now):
    lines = []

    for event in events[:CALENDAR_LIMIT]:
        active = event["start"] <= now < event["end"]

        status = "🟢 IN CORSO" if active else "⏳ In programma"

        lines.append(
            f"{event['icon']} **{event['name']}**\n"
            f"🕒 {discord_timestamp(event['start'], 'F')} "
            f"({discord_timestamp(event['start'], 'R')})\n"
            f"⏱️ Durata: {event['duration']} min · {status}"
        )

    description = "\n\n".join(lines)

    return {
        "username": "ARTYKO AION 2 EVENTS",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": "📅 ARTYKO | CALENDARIO EVENTI AION 2",
            "description": description or "Nessun evento disponibile.",
            "color": 0x00D9C0,
            "footer": {
                "text": (
                    "Server EU · Orari locali Discord · "
                    "Programmazione basata su AION2.APP"
                )
            },
            "timestamp": now.isoformat(),
        }],
    }


def build_reminder(event):
    return {
        "username": "ARTYKO AION 2 EVENTS",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": f"🔔 {event['icon']} {event['name']}",
            "description": (
                "**L'evento sta per iniziare!**\n\n"
                f"🕒 Inizio: {discord_timestamp(event['start'], 'F')}\n"
                f"⏳ Countdown: {discord_timestamp(event['start'], 'R')}\n"
                f"⏱️ Durata: {event['duration']} minuti\n"
                "🌍 Server: **EU**"
            ),
            "color": 0x39FF14,
            "footer": {
                "text": "ARTYKO | AION 2 EVENT REMINDER"
            },
        }],
    }


def event_key(event):
    return f"{event['id']}:{int(event['start'].timestamp())}"


def find_due_reminders(events, now, sent):
    due = []

    for event in events:
        seconds_until = (event["start"] - now).total_seconds()

        # Intervallo: da 5 minuti prima fino a 1 minuto prima.
        if not (
            60 <= seconds_until <= REMINDER_WINDOW_SECONDS
        ):
            continue

        key = event_key(event)

        if key not in sent:
            due.append(event)

    return due


def main():
    now = datetime.now(UTC)

    print("=" * 55)
    print("ARTYKO | AION 2 EVENTS")
    print("=" * 55)
    print("Server: EU")
    print("Fuso orario: Europe/Berlin")
    print("Modalita' sicura:", DRY_RUN)
    print("Webhook configurato:", bool(WEBHOOK_URL))
    print()

    events = calculate_events(now)
    state = load_state()

    print("PROSSIMI EVENTI")
    print("-" * 55)

    for event in events[:CALENDAR_LIMIT]:
        local_time = event["start"].astimezone(SERVER_TIMEZONE)

        print(
            f"{local_time:%d/%m/%Y %H:%M} | "
            f"{event['icon']} {event['name']} | "
            f"{event['duration']} min"
        )

    print()

    calendar = build_calendar(events, now)

    print("Calendario Discord preparato:")
    print(calendar["embeds"][0]["title"])

    sent = set(state["sent_reminders"])
    due = find_due_reminders(events, now, sent)

    print()
    print("Promemoria da inviare:", len(due))

    for event in due:
        print(
            f"  {event['icon']} {event['name']} "
            f"alle {event['start'].astimezone(SERVER_TIMEZONE):%H:%M}"
        )

    if DRY_RUN:
        print()
        print("MODALITA' SICURA: nessun messaggio Discord inviato.")
        print("Nessuna modifica allo storico.")
        print("Test completato.")
        return

    # L'invio reale verra' abilitato dopo i test.
    raise RuntimeError(
        "Pubblicazione Discord non ancora abilitata. "
        "Prima completare i test del calendario."
    )


if __name__ == "__main__":
    main()
