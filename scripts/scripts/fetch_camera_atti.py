import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.camera.it"
SOURCE_URL = "https://www.camera.it/leg19/167"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CameraMonitor/1.0)"
}


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def extract_documents(html: str):

    soup = BeautifulSoup(html, "html.parser")

    documents = []

    # i link ai PDF sono il riferimento più stabile
    for link in soup.find_all("a", href=True):

        href = link["href"]

        if not href.lower().endswith(".pdf"):
            continue

        pdf_url = href
        if pdf_url.startswith("/"):
            pdf_url = BASE_URL + pdf_url

        text = compact_spaces(link.get_text())

        documents.append(
            {
                "ramo": "Camera",
                "tipo_atto": "",
                "numero": "",
                "titolo": text,
                "link": pdf_url,
                "fonte": "documenti_stampati"
            }
        )

    return documents


def save_json(items, target_date_str):

    output_path = OUTPUT_DIR / f"camera_atti_{target_date_str}.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    return output_path


def main():

    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")

    target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    target_date_str = target_date.isoformat()

    print("Scarico ultimi documenti stampati della Camera")

    html = fetch_html(SOURCE_URL)

    documents = extract_documents(html)

    print(f"Documenti trovati: {len(documents)}")

    output_path = save_json(documents, target_date_str)

    print(f"File salvato in: {output_path}")


if __name__ == "__main__":
    main()