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
    "Accept": "text/html,application/pdf,*/*",
}


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.today() - timedelta(days=1)).date().isoformat()


def build_assemblea_url(target_date: str) -> str:
    year, month, day = target_date.split("-")
    return f"https://www.camera.it/leg19/187?slAnnoMese={year}{month}&slGiorno={day}&idSeduta="


def build_commissioni_url(target_date: str) -> str:
    year, month, day = target_date.split("-")
    return (
        "https://www.camera.it/leg19/824"
        f"?tipo=C&anno={year}&mese={month}&giorno={day}&view=filtered&pagina=#"
    )


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r.text


def extract_text_blocks_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    blocks = []

    for tag in soup.find_all(["tr", "p", "li", "div"]):
        text = compact(tag.get_text(" ", strip=True))
        if not text:
            continue
        if len(text) < 40:
            continue
        blocks.append(text)

    return blocks


def is_navigation_noise(text: str) -> bool:
    t = text.lower()

    noise_chunks = [
        "vai al contenuto",
        "menu di navigazione",
        "accesso rapido",
        "progetti di legge ultimi decreti legge esaminati",
        "calendario settimanale resoconti audizioni oggi in commissione",
        "assemblea giunte e commissioni audizioni indagini conoscitive",
        "camera dei deputati europa internazionale",
        "registro dei rappresentanti di interessi",
        "prenotazione eventi visitare montecitorio",
        "server error",
    ]

    return any(chunk in t for chunk in noise_chunks)


def matched_marittimo_keywords(text: str):
    patterns = {
        "trasporto marittimo": r"\btrasporto marittimo\b",
        "marittimo": r"\bmarittim[oaie]\w*\b",
        "navigazione": r"\bnavigazion\w*\b",
        "porto/porti": r"\bport[oi]\b",
        "shipping": r"\bshipping\b",
        "armatore": r"\barmator\w*\b",
        "nave/navi": r"\bnav[ei]\b",
        "logistica": r"\blogistic\w*\b",
        "cabotaggio": r"\bcabotagg\w*\b",
        "canale di suez": r"\bcanale di suez\b",
        "stretto di hormuz": r"\bstretto di hormuz\b",
        "blue economy": r"\bblue economy\b",
        "autorità portuale": r"\bautorità portual\w*\b",
        "adsp": r"\badsp\b",
    }

    hits = []
    for label, pattern in patterns.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(label)
    return hits


def infer_item_type(text: str) -> str:
    t = text.lower()

    if "audizion" in t:
        return "Audizione"
    if "emendament" in t or "proposte emendative" in t:
        return "Emendamenti"
    if "termine per la presentazione" in t:
        return "Termine emendamenti"
    if re.search(r"\b(a\.c\.|c\.)\s*\d+", text, flags=re.IGNORECASE):
        return "DDL / PDL"
    if re.search(r"\bdoc\.\s*[ivxlcdm]", text, flags=re.IGNORECASE):
        return "Documento"
    if "interrogazione" in t or "interpellanza" in t or "mozione" in t or "risoluzione" in t:
        return "Atto di indirizzo / controllo"
    return "Voce ODG"


def dedupe_items(items):
    seen = set()
    out = []

    for item in items:
        key = (item["fonte"], item["tipo"], item["snippet"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def scan_source(name: str, url: str):
    html = fetch_html(url)
    blocks = extract_text_blocks_from_html(html)

    relevant_items = []

    for block in blocks:
        if is_navigation_noise(block):
            continue

        keyword_hits = matched_marittimo_keywords(block)
        if not keyword_hits:
            continue

        relevant_items.append({
            "fonte": name,
            "tipo": infer_item_type(block),
            "snippet": block,
            "matched_keywords": keyword_hits,
        })

    return dedupe_items(relevant_items)


def main():
    target_date = get_target_date()

    assemblea_url = build_assemblea_url(target_date)
    commissioni_url = build_commissioni_url(target_date)

    print("Scansiono ODG Camera per contenuti futuri rilevanti:", target_date)

    assemblea_items = scan_source("ODG Assemblea", assemblea_url)
    commissioni_items = scan_source("ODG Commissioni", commissioni_url)

    all_items = dedupe_items(assemblea_items + commissioni_items)

    result = {
        "target_date": target_date,
        "sources": {
            "assemblea_url": assemblea_url,
            "commissioni_url": commissioni_url,
        },
        "count": len(all_items),
        "items": all_items,
    }

    out_path = OUTPUT_DIR / f"camera_odg_alerts_{target_date}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Salvato:", out_path)
    print("Elementi rilevanti trovati:", len(all_items))
    for item in all_items[:10]:
        print("-", item["fonte"], "|", item["tipo"], "|", item["matched_keywords"], "|", item["snippet"][:220])


if __name__ == "__main__":
    main()