import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CameraMonitor/1.0)"
}


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return datetime.strptime(sys.argv[1], "%Y-%m-%d").date()


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def extract_agenda_items(html: str, target_date_str: str):
    soup = BeautifulSoup(html, "html.parser")

    items = []

    # ⚠️ versione iniziale semplice: prendiamo tutte le righe lista
for li in soup.find_all("li"):
    text = li.get_text(strip=True)

    if not text or len(text) < 30:
        continue

    # filtro rumore (menu sito)
    blacklist = [
        "home",
        "la camera",
        "lavori",
        "deputati",
        "documenti",
        "comunicazione",
        "servizi",
        "agenda",
        "notizie",
        "temi dell'attività parlamentare",
        "amministrazione trasparente",
        "registro dei rappresentanti",
        "relazioni con i cittadini",
        "portale storico",
        "english",
    ]

    text_lower = text.lower()

    if any(b in text_lower for b in blacklist):
        continue

    # tieni solo righe "parlamentari"
    keywords = [
        "proposta di legge",
        "disegno di legge",
        "ddl",
        "audizione",
        "interrogazione",
        "interpellanza",
        "risoluzione",
        "ordine del giorno",
        "esame",
        "discussione",
        "conversione in legge",
    ]

    if not any(k in text_lower for k in keywords):
        continue

        items.append({
            "ramo": "Camera",
            "data": target_date_str,
            "organo": "Aula",
            "tipo": "ODG",
            "titolo": text,
            "numero": "",
            "link": "",
            "fonte": "agenda_camera"
        })

    return items


def save_json(items, target_date_str: str):
    path = OUTPUT_DIR / f"camera_agenda_{target_date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return path


def main():
    target_date = parse_target_date()
    target_date_str = target_date.isoformat()

    # ⚠️ URL base agenda Camera (poi lo raffiniamo)
    url = "https://www.camera.it/leg19/410"

    print("Scarico agenda Camera:", url)

    html = fetch_html(url)
    items = extract_agenda_items(html, target_date_str)

    print("Elementi trovati:", len(items))

    path = save_json(items, target_date_str)

    print("File salvato in:", path)


if __name__ == "__main__":
    main()