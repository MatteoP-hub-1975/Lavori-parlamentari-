import json
import re
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


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def extract_page_title(html):
    soup = BeautifulSoup(html, "html.parser")
    if soup.title:
        return compact(soup.title.get_text(" ", strip=True))
    return ""


def extract_odg_details(html):
    soup = BeautifulSoup(html, "html.parser")
    text = compact(soup.get_text(" ", strip=True))

    match = re.search(
        r"Ordine del giorno della seduta n\.?\s*\d+\s+del\s+\d{1,2}\s+\w+\s+\d{4}",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return compact(match.group(0))

    return ""


def enrich_link(url):
    url = (url or "").strip()
    if not url:
        return "", ""

    try:
        r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
        r.raise_for_status()
        final_url = r.url

        content_type = (r.headers.get("Content-Type") or "").lower()
        page_title = ""

        if "text/html" in content_type:
            odg_title = extract_odg_details(r.text)
            if odg_title:
                page_title = odg_title
            else:
                page_title = extract_page_title(r.text)

        return final_url, page_title
    except Exception:
        return url, ""


def extract_odg(soup):
    results = []

    for a in soup.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True))

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


def find_commissioni_permanenti_block(soup):
    markers = soup.find_all(string=re.compile(r"Commissioni permanenti", re.IGNORECASE))
    if not markers:
        return None

    marker = markers[0]
    current = marker.parent

    # risale un po' per prendere un contenitore utile
    for _ in range(4):
        if current is None:
            break
        if current.name in {"section", "div", "article"}:
            text = compact(current.get_text(" ", strip=True))
            if "Commissioni permanenti" in text:
                return current
        current = current.parent

    return marker.parent


def is_excluded_commission_link(text, link):
    combined = f"{text} {link}".lower()

    excluded_terms = [
        "bicamerali",
        "inchiesta",
        "giunte",
        "delegazioni",
        "comitato per la legislazione",
        "comitato legislazione",
        "speciali",
    ]

    return any(term in combined for term in excluded_terms)


def extract_commissioni(soup):
    results = []

    block = find_commissioni_permanenti_block(soup)
    if block is None:
        return results

    seen = set()

    for a in block.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True))

        if "Convocazione" not in text:
            continue

        raw_link = normalize_link(a.get("href"))
        final_link, page_title = enrich_link(raw_link)

        if is_excluded_commission_link(text, final_link):
            continue

        key = (text, final_link)
        if key in seen:
            continue
        seen.add(key)

        titolo = text
        if page_title:
            titolo = page_title

        results.append({
            "tipo": "Convocazione Commissione permanente",
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