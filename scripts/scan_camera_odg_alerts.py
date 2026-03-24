import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.today() - timedelta(days=1)).date().isoformat()


def build_commissioni_url(target_date: str) -> str:
    y, m, d = target_date.split("-")
    return f"https://www.camera.it/leg19/1099?giorno={d}&mese={m}&anno={y}"


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def classify_line(text: str):
    low = text.lower()

    if "audizion" in low:
        return "Audizione"

    if "termine per la presentazione" in low and (
        "emendament" in low or "proposte emendative" in low
    ):
        return "Termine emendamenti"

    if "emendament" in low or "proposte emendative" in low:
        return "Emendamenti"

    if re.search(r"\b(a\.c\.|c\.)\s*\d+", text, flags=re.IGNORECASE):
        return "DDL / PDL"

    if re.search(r"\b(doc\.)\s*[ivxlcdm]", text, flags=re.IGNORECASE):
        return "Documento"

    return None


def is_noise(text: str) -> bool:
    low = text.lower()

    noise_patterns = [
        "vai al contenuto",
        "menu di navigazione",
        "scrivi",
        "sito mobile",
        "accesso rapido",
        "prenotazione eventi",
        "visitare montecitorio",
        "registro dei rappresentanti di interessi",
        "camera dei deputati",
        "organi parlamentari",
        "conoscere la camera",
        "calendario settimanale",
        "resoconti",
        "oggi in commissione",
        "conferenze stampa",
        "interrogazioni, interpellanze, etc.",
        "votazioni",
        "ultimi dossier",
        "amministrazione trasparente",
        "social media policy",
        "privacy",
        "mappa del sito",
        "avviso legale",
        "accessibilità",
        "cookie",
    ]

    return any(pat in low for pat in noise_patterns)


def extract_relevant_items(text: str):
    lines = [compact(x) for x in text.split("\n")]
    items = []

    for line in lines:
        if len(line) < 40:
            continue

        if is_noise(line):
            continue

        tipo = classify_line(line)
        if not tipo:
            continue

        items.append({
            "tipo": tipo,
            "snippet": line
        })

    # dedup
    seen = set()
    clean = []
    for item in items:
        key = (item["tipo"], item["snippet"])
        if key in seen:
            continue
        seen.add(key)
        clean.append(item)

    return clean


def main():
    target_date = get_target_date()
    url = build_commissioni_url(target_date)

    print("Scansiono convocazioni Camera:", target_date)
    print("URL:", url)

    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    items = extract_relevant_items(text)

    result = {
        "target_date": target_date,
        "url": url,
        "count": len(items),
        "items": items,
    }

    out_path = OUTPUT_DIR / f"camera_odg_alerts_{target_date}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("Salvato:", out_path)
    print("Trovati:", len(items))
    for item in items[:10]:
        print("-", item["tipo"], "|", item["snippet"])


if __name__ == "__main__":
    main()