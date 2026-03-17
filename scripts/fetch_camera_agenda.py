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


def compact(text: str) -> str:
    return " ".join((text or "").split()).strip()


def extract_agenda_items(html: str, target_date_str: str):
    soup = BeautifulSoup(html, "html.parser")

    wanted_labels = {
        "ordine del giorno",
        "calendario dei lavori",
        "calendario settimanale",
        "resoconti",
        "audizioni",
        "oggi in commissione",
        "interrogazioni, interpellanze, mozioni, risoluzioni e odg",
        "audizioni e comunicazioni in commissione",
        "comunicazioni e informative urgenti in assemblea",
        "atti del governo e proposte di nomina sottoposti a parere",
        "atti di indirizzo e controllo",
        "indagini conoscitive",
        "giunte e commissioni",
        "assemblea",
        "commissioni",
    }

    items = []
    seen = set()

    for a in soup.find_all("a"):
        text = compact(a.get_text(" ", strip=True))
        if not text:
            continue

        text_lower = text.lower()

        if text_lower not in wanted_labels:
            continue

        if text_lower in seen:
            continue
        seen.add(text_lower)

        organo = "Camera"
        if "commission" in text_lower or "giunte e commissioni" in text_lower:
            organo = "Commissioni"
        elif "assemblea" in text_lower:
            organo = "Assemblea"

        items.append(
            {
                "ramo": "Camera",
                "data": target_date_str,
                "organo": organo,
                "tipo": "AGENDA",
                "titolo": text,
                "numero": "",
                "link": "",
                "fonte": "agenda_camera",
            }
        )

    return items


def save_json(items, target_date_str: str):
    path = OUTPUT_DIR / f"camera_agenda_{target_date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return path


def main():
    target_date = parse_target_date()
    target_date_str = target_date.isoformat()

    url = "https://www.camera.it/leg19/410"

    print("Scarico agenda Camera:", url)

    html = fetch_html(url)
    items = extract_agenda_items(html, target_date_str)

    print("Elementi trovati:", len(items))

    path = save_json(items, target_date_str)

    print("File salvato in:", path)


if __name__ == "__main__":
    main()