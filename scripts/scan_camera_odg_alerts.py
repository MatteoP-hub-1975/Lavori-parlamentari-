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


def build_commissioni_url(date):
    y, m, d = date.split("-")
    return f"https://www.camera.it/leg19/824?tipo=C&anno={y}&mese={m}&giorno={d}&view=filtered&pagina=#"


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def split_sentences(text):
    # spezza il testo in frasi "vere"
    return re.split(r"(?<=[\.\;])\s+", text)


def is_relevant(sentence):
    s = sentence.lower()

    return (
        "audizion" in s
        or "emendament" in s
        or "termine per la presentazione" in s
        or re.search(r"\b(c\.|a\.c\.)\s*\d+", s)
    )


def classify(sentence):
    s = sentence.lower()

    if "audizion" in s:
        return "Audizione"
    if "termine per la presentazione" in s:
        return "Termine emendamenti"
    if "emendament" in s:
        return "Emendamenti"
    if re.search(r"\b(c\.|a\.c\.)\s*\d+", s):
        return "DDL / PDL"

    return "Altro"


def main():
    target_date = get_target_date()
    url = build_commissioni_url(target_date)

    print("Scan ODG:", url)

    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    raw_text = soup.get_text("\n", strip=True)

    # TAGLIO il menu: prendo solo dopo il punto in cui iniziano le convocazioni vere
    start_idx = raw_text.lower().find("convocazioni")

    if start_idx == -1:
        start_idx = raw_text.lower().find("commissioni")

    filtered_text = raw_text[start_idx:] if start_idx != -1 else raw_text

    sentences = split_sentences(filtered_text)

    items = []

    for s in sentences:
        s = s.strip()

        if len(s) < 80:
            continue

        if not is_relevant(s):
            continue
        # elimina righe di navigazione anche se passano il filtro
        if "menu" in s.lower():
            continue
        if "vai al contenuto" in s.lower():
            continue
        if "camera dei deputati" in s.lower() and len(s) > 200:
            continue

        items.append({
            "tipo": classify(s),
            "snippet": s
        })

    # dedup
    seen = set()
    clean = []
    for i in items:
        if i["snippet"] in seen:
            continue
        seen.add(i["snippet"])
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