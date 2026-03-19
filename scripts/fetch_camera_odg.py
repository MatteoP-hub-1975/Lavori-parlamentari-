import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.camera.it"
AGENDA_URL = "https://www.camera.it/leg19/76?active_tab_3806=3788&alias=76&environment=camera_internet&element_id=agenda_lavori"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CameraMonitor/1.0)"
}


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return datetime.strptime(sys.argv[1], "%Y-%m-%d").date()


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def normalize_link(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    return urljoin(BASE_URL, href)


def is_pdf_like(url: str) -> bool:
    url_l = (url or "").lower()
    return (
        url_l.endswith(".pdf")
        or "getdocumento.ashx" in url_l
        or "tipodoc=pdf" in url_l
    )


def find_odg_link_in_agenda(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    candidates = []
    for a in soup.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True)).lower()
        href = normalize_link(a["href"])

        if text == "ordine del giorno":
            candidates.append(href)

    # preferisci un PDF diretto se presente
    for href in candidates:
        if is_pdf_like(href):
            return href

    return candidates[0] if candidates else ""


def extract_pdf_from_page(url: str) -> str:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # prima cerca link PDF espliciti
    for a in soup.find_all("a", href=True):
        href = normalize_link(a["href"])
        if is_pdf_like(href):
            return href

    # fallback: prova a trovare URL PDF nel testo/html
    html_text = str(soup)
    match = re.search(r'https?://[^"\']+(?:\.pdf|getDocumento\.ashx[^"\']+)', html_text, flags=re.IGNORECASE)
    if match:
        return match.group(0)

    return ""


def build_output_item(target_date_str: str, odg_link: str, source_link: str) -> dict:
    return {
        "ramo": "Camera",
        "data_pubblicazione": target_date_str,
        "organo": "Assemblea",
        "tipo_atto": "Ordine del giorno Assemblea",
        "titolo": "Ordine del giorno Assemblea",
        "commissione": "",
        "seduta": "",
        "link_pdf": odg_link,
        "link_source": source_link,
        "fonte": "agenda_lavori_camera",
    }


def save_json(items, target_date_str: str) -> Path:
    output_path = OUTPUT_DIR / f"camera_odg_{target_date_str}.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return output_path


def main():
    target_date = parse_target_date()
    target_date_str = target_date.isoformat()

    print("Scarico agenda Camera:", AGENDA_URL)
    agenda_html = fetch_html(AGENDA_URL)

    odg_href = find_odg_link_in_agenda(agenda_html)

    if not odg_href:
        print("Link 'Ordine del giorno' non trovato.")
        output_path = save_json([], target_date_str)
        print("File salvato in:", output_path)
        return

    odg_pdf = odg_href if is_pdf_like(odg_href) else extract_pdf_from_page(odg_href)

    if not odg_pdf:
        print("ODG trovato ma nessun PDF diretto individuato.")
        items = [build_output_item(target_date_str, "", odg_href)]
    else:
        print("ODG PDF individuato:", odg_pdf)
        items = [build_output_item(target_date_str, odg_pdf, odg_href)]

    output_path = save_json(items, target_date_str)

    print("ODG trovati:", len(items))
    print("File salvato in:", output_path)


if __name__ == "__main__":
    main()