import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.camera.it"
URL_ASSEMBLEA = "https://www.camera.it/leg19/207"
URL_COMMISSIONI = "https://www.camera.it/leg19/210"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}

MESI = {
    "gennaio": "01",
    "febbraio": "02",
    "marzo": "03",
    "aprile": "04",
    "maggio": "05",
    "giugno": "06",
    "luglio": "07",
    "agosto": "08",
    "settembre": "09",
    "ottobre": "10",
    "novembre": "11",
    "dicembre": "12",
}

def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()
    
def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def normalize_link(href, base_url):
    return urljoin(base_url, href or "")


def compact(text):
    return " ".join((text or "").split()).strip()


def parse_it_date(text):
    text = compact(text).lower()
    m = re.search(
        r"\b(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)\s+(\d{1,2})\s+([a-zàèéìòù]+)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return ""

    day, month_name, year = m.groups()
    month_num = MESI.get(month_name.lower())
    if not month_num:
        return ""

    return f"{year}-{month_num}-{day.zfill(2)}"


def extract_commissioni_resoconti(target_date):
    html = fetch_html(URL_COMMISSIONI)
    soup = BeautifulSoup(html, "html.parser")

    items = []

    # ogni riga utile è sostanzialmente:
    # "Martedì 17 marzo 2026" + "Scarica Pdf"
    for li in soup.find_all("li"):
        li_text = compact(li.get_text(" ", strip=True))
        if not li_text:
            continue

        data_iso = parse_it_date(li_text)
        if data_iso != target_date:
            continue

        pdf_link = ""
        for a in li.find_all("a", href=True):
            a_text = compact(a.get_text(" ", strip=True)).lower()
            if "scarica pdf" in a_text:
                pdf_link = normalize_link(a["href"], URL_COMMISSIONI)
                break

        if not pdf_link:
            continue

        items.append({
            "ramo": "Camera",
            "data": target_date,
            "tipo_atto": "Resoconto Commissioni",
            "titolo": f"Resoconto Commissioni – {li_text}",
            "data_resoconto": data_iso,
            "link_pdf": pdf_link,
            "categoria_preliminare": "Interesse istituzionale",
            "motivazione_preliminare": "Resoconto Camera - Giunte e Commissioni",
        })

    return items


def extract_assemblea_resoconti(target_date):
    # Per ora lasciamo vuoto o base minimale: la priorità era Commissioni.
    # Se vuoi, poi aggiungiamo la parte Assemblea con logica dedicata.
    return []


def main():
    target_date = get_target_date()

    print("Scarico resoconti Camera per data:", target_date)

    items = []
    items.extend(extract_commissioni_resoconti(target_date))
    items.extend(extract_assemblea_resoconti(target_date))

    output_path = OUTPUT_DIR / f"camera_resoconti_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("Trovati:", len(items))
    print("Salvato:", output_path)

    for item in items:
        print("-", item["titolo"], "|", item["link_pdf"])


if __name__ == "__main__":
    main()