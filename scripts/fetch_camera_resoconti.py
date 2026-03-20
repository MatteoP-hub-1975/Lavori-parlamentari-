import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.camera.it"
URL = "https://www.camera.it/leg19/207"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_target_date():
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()


def fetch_html():
    r = requests.get(URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def normalize_link(href):
    return urljoin(BASE_URL, href or "")


def main():
    target_date = get_target_date()

    print("Scarico resoconti Camera (reali)...")

    html = fetch_html()
    soup = BeautifulSoup(html, "html.parser")

    items = []

    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())

        # filtro intelligente
        if any(x in text.lower() for x in [
            "resoconto",
            "stenografico",
            "sommario"
        ]):
            items.append({
                "ramo": "Camera",
                "data": target_date,
                "tipo_atto": "Resoconto",
                "titolo": text,
                "link_pdf": normalize_link(a["href"]),
                "categoria_preliminare": "Interesse istituzionale",
                "motivazione_preliminare": "Resoconto Camera"
            })

    output_path = OUTPUT_DIR / f"camera_resoconti_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("Trovati:", len(items))
    print("Salvato:", output_path)

    for item in items[:5]:
        print("-", item["titolo"])


if __name__ == "__main__":
    main()