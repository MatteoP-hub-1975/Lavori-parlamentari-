import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


URL = "https://www.camera.it/leg19/76?active_tab_3806=3788&alias=76&environment=camera_internet&element_id=agenda_lavori"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_target_date():
    # automatico: ieri
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()


def fetch_html():
    r = requests.get(URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def normalize_link(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return "https://www.camera.it" + href


def extract_odg(soup):
    results = []

    for a in soup.find_all("a"):
        text = a.get_text(" ", strip=True)

        if "Ordine del giorno" in text:
            results.append({
                "tipo": "ODG Assemblea",
                "titolo": text,
                "link": normalize_link(a.get("href"))
            })
            break  # uno solo

    return results


def extract_commissioni(soup):
    results = []

    for a in soup.find_all("a"):
        text = a.get_text(" ", strip=True)

        # prendiamo solo convocazioni
        if "Convocazione" in text:
            link = normalize_link(a.get("href"))

            # filtro anti rumore
            if any(x in link.lower() for x in [
                "bicamerali", "inchiesta", "giunte",
                "delegazioni", "comitato", "speciali"
            ]):
                continue

            results.append({
                "tipo": "Convocazione Commissione",
                "titolo": text,
                "link": link
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
            "motivazione_preliminare": "Agenda lavori Camera"
        })

    output_path = OUTPUT_DIR / f"camera_agenda_operativa_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("Trovati:", len(items))
    print("Salvato:", output_path)


if __name__ == "__main__":
    main()