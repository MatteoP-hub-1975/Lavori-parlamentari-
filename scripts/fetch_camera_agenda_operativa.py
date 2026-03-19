import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


URL = "https://www.camera.it/leg19/76?active_tab_3806=3788&alias=76&environment=camera_internet&element_id=agenda_lavori"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/pdf,*/*",
}


def get_target_date():
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()


def fetch_html(url=URL):
    r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r.text


def normalize_link(href, base_url=URL):
    href = (href or "").strip()
    if not href:
        return ""
    return urljoin(base_url, href)


def resolve_final_link(url):
    url = (url or "").strip()
    if not url:
        return ""

    try:
        r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
        r.raise_for_status()
        return r.url
    except Exception:
        return url


def extract_page_title(html):
    soup = BeautifulSoup(html, "html.parser")
    if soup.title:
        return " ".join(soup.title.get_text(" ", strip=True).split()).strip()
    return ""


def enrich_link(url):
    """
    Restituisce:
    - link finale risolto
    - titolo pagina finale se disponibile
    """
    url = (url or "").strip()
    if not url:
        return "", ""

    try:
        r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
        r.raise_for_status()
        final_url = r.url

        content_type = (r.headers.get("Content-Type") or "").lower()

        if "text/html" in content_type:
            page_title = extract_page_title(r.text)
        else:
            page_title = ""

        return final_url, page_title
    except Exception:
        return url, ""


def extract_odg(soup):
    results = []

    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split()).strip()

        if "Ordine del giorno" in text:
            raw_link = normalize_link(a.get("href"))
            final_link, page_title = enrich_link(raw_link)

            titolo = text
            if page_title:
                titolo = page_title

            results.append({
                "tipo": "ODG Assemblea",
                "titolo": titolo,
                "link": final_link,
            })
            break

    return results


def extract_commissioni(soup):
    results = []

    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split()).strip()

        if "Convocazione" in text:
            raw_link = normalize_link(a.get("href"))
            final_link, page_title = enrich_link(raw_link)

            link_check = final_link.lower()

            if any(x in link_check for x in [
                "bicamerali",
                "inchiesta",
                "giunte",
                "delegazioni",
                "comitato",
                "speciali",
            ]):
                continue

            titolo = text
            if page_title:
                titolo = page_title

            results.append({
                "tipo": "Convocazione Commissione",
                "titolo": titolo,
                "link": final_link,
            })

    return results


def main():
    target_date = get_target_date()

    print("Scarico agenda Camera...")

    html = fetch_html()
    soup = BeautifulSoup(html, "html.parser")

    odg = extract_odg(soup)
    commissioni = extract_commissioni(soup)

    items = []

    for x in odg + commissioni:
        items.append({
            "ramo": "Camera",
            "data": target_date,
            "tipo_atto": x["tipo"],
            "titolo": x["titolo"],
            "link_pdf": x["link"],
            "categoria_preliminare": "Interesse istituzionale",
            "motivazione_preliminare": "Agenda lavori Camera",
        })

    output_path = OUTPUT_DIR / f"camera_agenda_operativa_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("Trovati:", len(items))
    print("Salvato:", output_path)

    for item in items:
        print("-", item["tipo_atto"], "|", item["titolo"], "|", item["link_pdf"])


if __name__ == "__main__":
    main()