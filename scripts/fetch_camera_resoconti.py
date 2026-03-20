import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.camera.it"

URL_ASSEMBLEA = "https://www.camera.it/leg19/410"
URL_COMMISSIONI = "https://www.camera.it/leg19/824"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_target_date():
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def normalize_link(href):
    if not href:
        return ""
    return urljoin(BASE_URL, href)


def compact(text):
    return " ".join((text or "").split()).strip()


def extract_resoconti(url, tipo):
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    results = []

    for a in soup.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True))

        if not text:
            continue

        # filtro per evitare link inutili
        if len(text) < 15:
            continue

        link = normalize_link(a.get("href"))

        # filtro base resoconti
        if any(x in text.lower() for x in [
            "resoconto",
            "seduta",
            "stenografico",
            "sommario"
        ]):
            results.append({
                "tipo": tipo,
                "titolo": text,
                "link": link
            })

    return results


def main():
    target_date = get_target_date()

    print("Scarico resoconti Camera...")

    assemblea = extract_resoconti(URL_ASSEMBLEA, "Resoconto Assemblea")
    commissioni = extract_resoconti(URL_COMMISSIONI, "Resoconto Commissione")

    items = []

    for x in assemblea + commissioni:
        items.append({
            "ramo": "Camera",
            "data": target_date,
            "tipo_atto": x["tipo"],
            "titolo": x["titolo"],
            "link_pdf": x["link"],
            "categoria_preliminare": "Interesse istituzionale",
            "motivazione_preliminare": "Resoconto Camera",
        })

    output_path = OUTPUT_DIR / f"camera_resoconti_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("Trovati:", len(items))
    print("Salvato:", output_path)

    for item in items[:5]:
        print("-", item["tipo_atto"], "|", item["titolo"])


if __name__ == "__main__":
    main()