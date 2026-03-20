import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.camera.it"

URL_STENOGRAFICO = "https://www.camera.it/leg19/410?tipo=alfabetico_stenografico"
URL_SOMMARIO = "https://www.camera.it/leg19/410?tipo=sommario"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_target_date():
    return (datetime.today() - timedelta(days=1)).date().isoformat()


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def normalize_link(href, base):
    if not href:
        return ""
    return urljoin(base, href)


def compact(text):
    return " ".join((text or "").split()).strip()


def extract_latest_resoconto(url, tipo):
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    results = []

    for a in soup.find_all("a", href=True):
        text = compact(a.get_text())

        # filtro forte
        if not any(x in text.lower() for x in ["seduta", "resoconto"]):
            continue

        link = normalize_link(a.get("href"), url)

        # deve essere documento vero, non pagina indice
        if not any(x in link.lower() for x in [
            "stenografico",
            "sommario",
            "pdf",
            "resoconto"
        ]):
            continue

        results.append({
            "tipo": tipo,
            "titolo": text,
            "link": link
        })

    # prendiamo solo i primi (più recenti)
    return results[:5]


def main():
    target_date = get_target_date()

    print("Scarico resoconti Camera (Assemblea)...")

    stenografici = extract_latest_resoconto(
        URL_STENOGRAFICO,
        "Resoconto Assemblea (stenografico)"
    )

    sommari = extract_latest_resoconto(
        URL_SOMMARIO,
        "Resoconto Assemblea (sommario)"
    )

    items = []

    for x in stenografici + sommari:
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

    for i in items:
        print("-", i["tipo_atto"], "|", i["titolo"])


if __name__ == "__main__":
    main()