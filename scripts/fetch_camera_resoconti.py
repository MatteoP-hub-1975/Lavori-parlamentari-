import json
import re
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
    r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r.text


def normalize_link(href, base_url):
    href = (href or "").strip()
    if not href:
        return ""
    return urljoin(base_url, href)


def compact(text):
    return " ".join((text or "").split()).strip()


def is_good_resoconto_text(text):
    text_l = text.lower()

    positive = [
        "resoconto stenografico",
        "resoconto sommario",
        "resoconto",
        "sommario",
        "stenografico",
    ]

    negative = [
        "parlamento in seduta comune",
        "documenti di seduta",
        "ordine del giorno",
        "agenda dei lavori",
        "calendario dei lavori",
        "programma dei lavori",
    ]

    if any(x in text_l for x in negative):
        return False

    return any(x in text_l for x in positive)


def is_good_resoconto_link(link):
    link_l = link.lower()

    # escludi link troppo generici o di navigazione
    negative = [
        "/leg19/76",
        "/leg19/187",
        "/leg19/410",
        "/leg19/824",
    ]

    if any(x == link_l for x in negative):
        return False

    # includi solo link che sembrano davvero resoconti/documenti di seduta
    positive = [
        "resoconto",
        "stenografico",
        "sommario",
        "documentiparlamentari",
        "getdocumento.ashx",
    ]

    return any(x in link_l for x in positive)


def dedupe(items):
    seen = set()
    out = []

    for item in items:
        key = (item["tipo"], item["titolo"], item["link"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def extract_resoconti(url, tipo):
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    results = []

    for a in soup.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True))
        if not text:
            continue

        link = normalize_link(a.get("href"), url)

        if not is_good_resoconto_text(text):
            continue

        if not is_good_resoconto_link(link):
            continue

        results.append({
            "tipo": tipo,
            "titolo": text,
            "link": link,
        })

    return dedupe(results)


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

    for item in items[:10]:
        print("-", item["tipo_atto"], "|", item["titolo"], "|", item["link_pdf"])


if __name__ == "__main__":
    main()