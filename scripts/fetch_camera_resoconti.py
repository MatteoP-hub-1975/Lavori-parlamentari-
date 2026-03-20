import json
import re
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
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def normalize_link(href):
    return urljoin(BASE_URL, href or "")


def compact(text):
    return " ".join((text or "").split()).strip()


def extract_resoconto_links(soup):
    links = []
    for a in soup.find_all("a", href=True):
        if "Vai al resoconto" in a.get_text():
            links.append(normalize_link(a["href"]))
    return links


def extract_date_from_page(html):
    soup = BeautifulSoup(html, "html.parser")
    text = compact(soup.get_text(" ", strip=True)).lower()

    # cerca pattern tipo "19 marzo 2026"
    m = re.search(r"\b(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})\b", text)
    if not m:
        return ""

    giorno, mese, anno = m.groups()
    mese_num = MESI.get(mese.lower())

    if not mese_num:
        return ""

    giorno = giorno.zfill(2)

    return f"{anno}-{mese_num}-{giorno}"


def extract_seduta_from_page(html):
    text = compact(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    m = re.search(r"seduta\s*n\.?\s*(\d+)", text, flags=re.IGNORECASE)
    if m:
        return f"Seduta n. {m.group(1)}"
    return ""


def main():
    target_date = get_target_date()

    print("Scarico resoconti Camera e filtro per ieri:", target_date)

    html = fetch_html(URL)
    soup = BeautifulSoup(html, "html.parser")

    links = extract_resoconto_links(soup)

    items = []

    for link in links:
        try:
            page_html = fetch_html(link)

            data_resoconto = extract_date_from_page(page_html)

            if data_resoconto != target_date:
                continue  # filtro qui

            seduta = extract_seduta_from_page(page_html)

            titolo = "Resoconto Camera"
            if seduta:
                titolo += f" – {seduta}"

            items.append({
                "ramo": "Camera",
                "data": target_date,
                "tipo_atto": "Resoconto",
                "titolo": titolo,
                "data_resoconto": data_resoconto,
                "seduta": seduta,
                "link_pdf": link,
                "categoria_preliminare": "Interesse istituzionale",
                "motivazione_preliminare": "Resoconto Camera",
            })

        except Exception as e:
            print("Errore su link:", link)

    output_path = OUTPUT_DIR / f"camera_resoconti_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("Trovati (ieri):", len(items))
    print("Salvato:", output_path)

    for item in items:
        print("-", item["titolo"], "|", item["data_resoconto"])


if __name__ == "__main__":
    main()