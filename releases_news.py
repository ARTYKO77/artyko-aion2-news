


import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# ============================================
# ARTYKO GAME RELEASES V5.2 - PREMIUM
# Pubblicazione protetta da RELEASES_DRY_RUN
# ============================================

ROOT = Path(__file__).resolve().parent
TZ = ZoneInfo("Europe/Rome")
NOW = datetime.now(TZ)
TODAY = NOW.date()

PREMIUM_FILE = ROOT / "releases_premium.json"
SOURCES_FILE = ROOT / "releases_sources.json"
VERIFIED_FILE = ROOT / "releases_verified.json"
SEEN_FILE = ROOT / "releases_seen.json"
COVER_FILE = ROOT / "releases_cover.png"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = {
    name.upper(): index
    for index, name in enumerate(
        [
            "January", "February", "March",
            "April", "May", "June",
            "July", "August", "September",
            "October", "November", "December",
        ],
        start=1,
    )
}

ENTRY_PATTERN = re.compile(
    r"^(.+?)\s+[-–—]\s+"
    r"([A-Za-z]+)\s+(\d{1,2})"
    r"(?:,\s*(20\d{2}))?"
    r"(?:\s+\[([^\]]+)\])?\s*$"
)

PLATFORM_PATTERN = re.compile(
    r"^(.*?)\s*\(([^()]*)\)$"
)

EXCLUDED_CONTENT = (
    "demo",
    "playtest",
    "soundtrack",
    "artbook",
    "art book",
    "wallpaper",
    "dedicated server",
    "beta test",
    "test server",
)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def normalize(value):
    value = (value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"File obbligatorio mancante: {path.name}"
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Formato JSON non valido: {path.name}"
        )

    return data


def phrase_matches(title, phrase):
    title_words = normalize(title).split()
    phrase_words = normalize(phrase).split()

    if not phrase_words:
        return False

    size = len(phrase_words)

    return any(
        title_words[i:i + size] == phrase_words
        for i in range(
            len(title_words) - size + 1
        )
    )


def matches_any(title, phrases):
    return any(
        phrase_matches(title, phrase)
        for phrase in phrases
        if isinstance(phrase, str)
    )


def is_excluded(title, premium):
    if matches_any(title, EXCLUDED_CONTENT):
        return True

    return matches_any(
        title,
        premium.get("exclude_editions", [])
    )


def premium_category(title, premium):
    if matches_any(
        title,
        premium.get("approved_games", [])
    ):
        return "Titolo approvato"

    if matches_any(
        title,
        premium.get("major_mmos", [])
    ):
        return "MMORPG / MMO"

    if matches_any(
        title,
        premium.get("major_franchises", [])
    ):
        return "Grande franchise"

    return None


def parse_steam_date(value):
    value = re.sub(
        r"\s+", " ", value or ""
    ).strip()

    for fmt in (
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b, %Y",
        "%d %B, %Y",
    ):
        try:
            return datetime.strptime(
                value, fmt
            ).date()
        except ValueError:
            continue

    return None


def fetch_steam(today, end_date):
    games = []
    pages_ok = 0

    for page in range(10):
        try:
            response = SESSION.get(
                "https://store.steampowered.com/search/results/",
                params={
                    "start": page * 50,
                    "count": 50,
                    "filter": "popularcomingsoon",
                    "supportedlang": "english",
                    "infinite": "1",
                },
                timeout=25,
            )
            response.raise_for_status()

            html = response.json().get(
                "results_html", ""
            )

            rows = BeautifulSoup(
                html, "html.parser"
            ).select("a.search_result_row")

            pages_ok += 1

            print(
                f"Steam pagina {page + 1}: "
                f"{len(rows)} giochi"
            )

            if not rows:
                break

            for row in rows:
                appid = str(
                    row.get("data-ds-appid", "")
                ).split(",")[0]

                title_node = row.select_one(
                    ".title"
                )
                date_node = row.select_one(
                    ".search_released"
                )

                if not (
                    appid.isdigit()
                    and title_node
                    and date_node
                ):
                    continue

                title = title_node.get_text(
                    " ", strip=True
                )

                release_date = parse_steam_date(
                    date_node.get_text(
                        " ", strip=True
                    )
                )

                if (
                    release_date is None
                    or not today <= release_date <= end_date
                ):
                    continue

                games.append({
                    "title": title,
                    "date": release_date,
                    "platforms": "PC",
                    "url": (
                        "https://store.steampowered.com/"
                        f"app/{appid}/"
                    ),
                    "sources": ["Steam"],
                    "note": "",
                })

            time.sleep(0.2)

        except (
            requests.RequestException,
            ValueError,
        ) as exc:
            print(
                f"Errore Steam pagina {page + 1}: "
                f"{exc}"
            )

    if pages_ok == 0:
        print(
            "ATTENZIONE: Steam non disponibile."
        )

    return games


def fetch_gamesradar(config, today, end_date):
    sources = config.get(
        "editorial_sources", []
    )

    source = next(
        (
            item for item in sources
            if (
                item.get("name") == "GamesRadar"
                and item.get("enabled")
            )
        ),
        None,
    )

    if not source:
        print("GamesRadar disabilitato.")
        return []

    response = SESSION.get(
        source["url"], timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text, "html.parser"
    )

    games = []

    for heading in soup.select("h2, h3"):
        heading_text = heading.get_text(
            " ", strip=True
        ).upper()

        if "GAMES OF" not in heading_text:
            continue

        month_name = next(
            (
                name for name in MONTHS
                if re.search(
                    rf"\b{name}\b",
                    heading_text
                )
            ),
            None,
        )

        year_match = re.search(
            r"\b20\d{2}\b",
            heading_text
        )

        if not month_name or not year_match:
            continue

        section_year = int(
            year_match.group()
        )
        section_month = MONTHS[month_name]

        month_index = (
            section_year * 12 + section_month
        )
        start_index = (
            today.year * 12 + today.month
        )
        end_index = (
            end_date.year * 12 + end_date.month
        )

        if not (
            start_index <= month_index <= end_index
        ):
            continue

        sibling = heading.find_next_sibling()

        while (
            sibling
            and sibling.name not in ("h2", "h3")
        ):
            if sibling.name in ("ul", "ol"):
                for li in sibling.find_all(
                    "li", recursive=False
                ):
                    text = li.get_text(
                        " ", strip=True
                    )

                    match = ENTRY_PATTERN.match(
                        text
                    )

                    if not match:
                        continue

                    (
                        info,
                        month_text,
                        day_text,
                        year_text,
                        note,
                    ) = match.groups()

                    month_number = MONTHS.get(
                        month_text.upper()
                    )

                    if not month_number:
                        continue

                    year = int(
                        year_text or section_year
                    )

                    try:
                        release_date = datetime(
                            year,
                            month_number,
                            int(day_text),
                        ).date()
                    except ValueError:
                        continue

                    if not (
                        today <= release_date <= end_date
                    ):
                        continue

                    platform_match = (
                        PLATFORM_PATTERN.match(
                            info.strip()
                        )
                    )

                    if platform_match:
                        title = (
                            platform_match.group(1)
                            .strip()
                        )
                        platforms = (
                            platform_match.group(2)
                            .strip()
                        )
                    else:
                        title = info.strip()
                        platforms = (
                            "Non specificate"
                        )

                    games.append({
                        "title": title,
                        "date": release_date,
                        "platforms": platforms,
                        "url": source["url"],
                        "sources": ["GamesRadar"],
                        "note": note or "",
                    })

            sibling = sibling.find_next_sibling()

    print(
        f"GamesRadar: {len(games)} "
        "uscite nel periodo"
    )

    return games


def merge_games(games):
    merged = {}

    for game in games:
        key = (
            normalize(game["title"]),
            game["date"].isoformat(),
        )

        if key not in merged:
            merged[key] = {
                **game,
                "sources": list(
                    game["sources"]
                ),
            }
            continue

        existing = merged[key]

        for source in game["sources"]:
            if source not in existing["sources"]:
                existing["sources"].append(
                    source
                )

        if len(game["platforms"]) > len(
            existing["platforms"]
        ):
            existing["platforms"] = (
                game["platforms"]
            )

        if (
            "store.steampowered.com"
            in game["url"]
        ):
            existing["url"] = game["url"]

        if (
            game["note"]
            and not existing["note"]
        ):
            existing["note"] = (
                game["note"]
            )

    return list(merged.values())


def select_premium(games, premium, limit):
    selected = []

    for game in games:
        title = game["title"]

        if is_excluded(title, premium):
            continue

        category = premium_category(
            title, premium
        )

        if not category:
            continue

        selected.append({
            **game,
            "category": category,
        })

    selected.sort(
        key=lambda game: (
            game["date"],
            game["title"].casefold(),
        )
    )

    return selected[:limit]



def load_seen():
    if not SEEN_FILE.exists():
        return {"last_published_date": None, "published_games": []}
    data = load_json(SEEN_FILE)
    if not isinstance(data.get("published_games", []), list):
        raise ValueError("published_games deve essere una lista")
    return data


def verified_candidates(selected, verified):
    approved = verified.get("verified_releases", [])
    if not isinstance(approved, list):
        raise ValueError("verified_releases deve essere una lista")
    result = []
    for game in selected:
        for item in approved:
            if not isinstance(item, dict):
                continue
            if (normalize(item.get("title")) == normalize(game["title"])
                    and item.get("date") == game["date"].isoformat()):
                official = item.get("official_url", "")
                if not (isinstance(official, str) and official.startswith("https://")):
                    print("Saltato: link ufficiale HTTPS assente:", game["title"])
                    continue
                result.append({**game, "platforms": item.get("platforms") or game["platforms"],
                               "official_url": official})
                break
    return result


def game_key(game):
    return normalize(game["title"]) + "|" + game["date"].isoformat()


def send_discord(games):
    webhook = os.environ.get("DISCORD_WEBHOOK_RELEASES", "")
    if not webhook.startswith("https://discord.com/api/webhooks/"):
        raise RuntimeError("Webhook Discord mancante o non valido")
    lines = []
    for game in games:
        lines.append(f"**{game['title']}** — {game['date'].strftime('%d/%m/%Y')}\n"
                     f"Piattaforme: {game['platforms']}\n"
                     f"[Fonte ufficiale]({game['official_url']})")
    description = "\n\n".join(lines)
    if len(description) > 4000:
        raise ValueError("Calendario troppo lungo per un singolo embed")
    embed = {"title": "🎮 ARTYKO | GAME RELEASES PREMIUM",
             "description": description,
             "color": 0x23B7B1,
             "footer": {"text": "Solo uscite approvate • Orario italiano"}}
    payload = {"username": "ARTYKO GAME RELEASES", "embeds": [embed]}
    # wait=true richiede a Discord di restituire il messaggio creato.
    # Non ripetere automaticamente POST in caso di timeout: l'invio potrebbe essere riuscito.
    webhook = webhook + ("&" if "?" in webhook else "?") + "wait=true"
    if COVER_FILE.is_file():
        embed["image"] = {"url": "attachment://releases_cover.png"}
        with COVER_FILE.open("rb") as cover:
            response = SESSION.post(webhook,
                data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                files={"files[0]": ("releases_cover.png", cover, "image/png")},
                timeout=30)
    else:
        response = SESSION.post(webhook, json=payload, timeout=30)
    response.raise_for_status()
    try:
        message = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Discord ha risposto senza un ID messaggio valido. "
            "Controllare il canale prima di un nuovo tentativo."
        ) from exc
    message_id = str(message.get("id", ""))
    if not message_id.isdigit():
        raise RuntimeError(
            "ID messaggio Discord non ricevuto. "
            "Controllare il canale prima di un nuovo tentativo."
        )
    return message_id


def main():
    print("=" * 42)
    print("ARTYKO GAME RELEASES V5.2 PREMIUM")
    print("=" * 42)
    now = datetime.now(TZ)
    today = now.date()
    dry_run = os.getenv("RELEASES_DRY_RUN", "true").lower() != "false"
    print("Ora italiana:", now.isoformat())
    print("Simulazione:", dry_run)

    premium = load_json(PREMIUM_FILE)
    config = load_json(SOURCES_FILE)
    verified = load_json(VERIFIED_FILE)
    seen = load_seen()
    days = int(config.get("days_ahead", 7))
    limit = int(config.get("max_games", 10))
    if not 1 <= days <= 31 or not 1 <= limit <= 10:
        raise ValueError("days_ahead o max_games fuori intervallo")
    end_date = today + timedelta(days=days - 1)
    print("Periodo:", today, "-", end_date)

    games = []
    try:
        games.extend(fetch_gamesradar(config, today, end_date))
    except (requests.RequestException, ValueError, KeyError) as exc:
        print("Errore GamesRadar:", exc)
    if config.get("steam", {}).get("enabled", True):
        games.extend(fetch_steam(today, end_date))
    else:
        print("Steam disabilitato da configurazione")

    selected = select_premium(merge_games(games), premium, limit)
    confirmed = verified_candidates(selected, verified)
    previous = set(seen.get("published_games", []))
    fresh = [game for game in confirmed if game_key(game) not in previous]
    print("\n=== CANDIDATI PREMIUM DA VERIFICARE ===")
    if not selected:
        print("Nessun candidato PREMIUM trovato.")
    for index, game in enumerate(selected, start=1):
        print(f"Candidato {index}:")
        print("  Titolo:", game["title"])
        print("  Data:", game["date"].isoformat())
        print("  Piattaforme:", game["platforms"])
        print("  Categoria:", game["category"])
        print("  Fonti:", ", ".join(game["sources"]))
        print("  URL:", game["url"])
        print("  Verifica ufficiale: DA ESEGUIRE")
    print("=== FINE CANDIDATI ===\n")
    print("Premium individuati:", len(selected))
    print("Corrispondenze con registro verificato:", len(confirmed))
    print("Nuove uscite approvate:", len(fresh))
    for game in fresh:
        print("-", game["title"], game["date"], game["platforms"], game["official_url"])

    if seen.get("last_published_date") == today.isoformat():
        print("Riepilogo già pubblicato oggi: nessun invio")
        return
    if not fresh:
        print("Nessuna nuova uscita approvata: nessun invio")
        return
    if dry_run:
        print("SIMULAZIONE COMPLETATA: nessun messaggio Discord, storico invariato")
        return

    try:
        message_id = send_discord(fresh)
    except requests.RequestException as exc:
        raise RuntimeError(
            "Invio Discord fallito o incerto. NON ripetere publish=true "
            "prima di controllare manualmente il canale Discord."
        ) from exc
    print("Discord ha confermato il messaggio ID:", message_id)
    seen["last_discord_message_id"] = message_id
    seen["last_published_date"] = today.isoformat()
    seen["published_games"] = sorted(previous | {game_key(game) for game in fresh})
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Riepilogo inviato; storico aggiornato")


if __name__ == "__main__":
    main()
