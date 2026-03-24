import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.today() - timedelta(days=1)).date().isoformat()


def build_commissioni_url(target_date: str):
    y, m, d = target_date.split("-")
    return f"https://www.camera.it/leg19/824?tipo=C&anno={y}&mese={m}&giorno={d}&view=filtered&pagina=#"


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def compact(text):
    return re.sub(r"\s+", " ", text).strip()


def extract_blocks(html):
    soup = BeautifulSoup(html, "html.parser")

    blocks = []

    for tag in soup.find_all(["tr"]):  # SOLO righe tabella (ODG vero)
        txt = compact(tag.get_text(" ", strip=True))

        if len(txt) < 60:
            continue

        # elimina menu e robaccia
        if "menu di navigazione" in txt.lower():
            continue
        if "vai al contenuto" in txt.lower():
            continue
        if "camera dei deputati" in txt.lower() and len(txt) > 500:
            continue

        blocks.append(txt)

    return blocks

def classify_block(text):
    t = text.lower()

    if "audizion" in t:
        return "Audizione"

    if "termine per la presentazione" in t:
        return "Termine emendamenti"

    if "emendament" in t:
        return "Emendamenti"

    if re.search(r"\b(c\.|a\.c\.)\s*\d+", text):
        return "DDL / PDL"

    return None

def main():
    target_date = get_target_date()

    url = build_commissioni_url(target_date)

    print("Scan ODG Commissioni:", target_date)
    print("URL:", url)

    html = fetch_html(url)
    blocks = extract_blocks(html)

    items = []

    for b in blocks:
        tipo = classify_block(b)
        if not tipo:
            continue

        items.append({
            "tipo": tipo,
            "snippet": b
        })

    # dedup
    seen = set()
    clean = []
    for i in items:
        key = i["snippet"]
        if key in seen:
            continue
        seen.add(key)
        clean.append(i)

    result = {
        "target_date": target_date,
        "count": len(clean),
        "items": clean
    }

    out_path = OUTPUT_DIR / f"camera_odg_alerts_{target_date}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("Trovati:", len(clean))
    for x in clean[:5]:
        print("-", x["tipo"], "|", x["snippet"][:200])


if __name__ == "__main__":
    main()