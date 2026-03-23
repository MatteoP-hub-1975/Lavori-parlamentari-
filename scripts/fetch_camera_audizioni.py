import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
from pathlib import Path
import sys


URL = "https://www.camera.it/leg19/546?tipo=elencoAudizioni"
BASE_URL = "https://www.camera.it"
OUTPUT_DIR = Path("data/camera")
HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text):
    return " ".join((text or "").split()).strip()


def parse_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return "no-date"


def main():
    target_date = parse_target_date()

    print("Scarico audizioni Camera...")

    res = requests.get(URL, headers=HEADERS, timeout=60)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    links = soup.find_all("a", href=True)

    results = []

    for a in links:
        text = compact(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not text or not href:
            continue

        if "audizion" not in text.lower():
            continue

        full_href = urljoin(BASE_URL, href)

        if "audiz=" not in full_href:
            continue

        results.append({
            "tipo_atto": "Audizione",
            "titolo": text,
            "link_pdf": full_href
        })

    print(f"Trovate audizioni: {len(results)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"camera_audizioni_{target_date}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Salvato: {output_file}")


if __name__ == "__main__":
    main()