import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.camera.it"
URL_TEMPLATE = (
    "https://www.camera.it/leg19/824"
    "?tipo=C&anno={anno}&mese={mese}&giorno={giorno}&view=filtered&pagina=#"
)

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text: str) -> str:
    return " ".join((text or "").split()).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


def build_url(target_date: str) -> str:
    anno, mese, giorno = target_date.split("-")
    return URL_TEMPLATE.format(anno=anno, mese=mese, giorno=giorno)


def normalize_link(href: str, base_url: str) -> str:
    return urljoin(base_url, href or "")


def clean_title(text: str) -> str:
    text = compact(text)
    text = re.sub(r"\bscarica pdf\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bresoconto stenografico\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bresoconto sommario\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bvideo\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -|")
    return text


def is_probably_menu_text(text: str) -> bool:
    t = text.lower()
    bad_chunks = [
        "calendario settimanale",
        "resoconti",
        "audizioni",
        "oggi in commissione",
        "assemblea",
        "giunte e commissioni",
        "indagini conoscitive",
        "stenografici delle commissioni",
        "bollettino degli organi collegiali",
    ]
    return any(chunk in t for chunk in bad_chunks)


def find_candidate_blocks(soup):
    candidates = []
    seen = set()

    for tag in soup.find_all(["div", "li", "p", "td", "section", "article"]):
        text = compact(tag.get_text(" ", strip=True))
        if not text:
            continue
        if "audizion" not in text.lower():
            continue
        if is_probably_menu_text(text):
            continue
        if len(text) < 40:
            continue

        key = text[:300]
        if key in seen:
            continue
        seen.add(key)
        candidates.append(tag)

    return candidates


def extract_first_document_link(container, base_url):
    for a in container.find_all("a", href=True):
        href = normalize_link(a.get("href", "").strip(), base_url)
        txt = compact(a.get_text(" ", strip=True)).lower()

        if (
            "documenti.camera.it" in href.lower()
            or "getdocumento.ashx" in href.lower()
            or href.lower().endswith(".pdf")
            or "scarica pdf" in txt
        ):
            return href

    for a in container.find_all("a", href=True):
        href = normalize_link(a.get("href", "").strip(), base_url)
        if "audiz=" in href.lower():
            return href

    return ""


def main():
    target_date = parse_target_date()
    url = build_url(target_date)

    print("Scarico audizioni Camera per data:", target_date)
    print("URL:", url)

    res = requests.get(url, headers=HEADERS, timeout=60)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    blocks = find_candidate_blocks(soup)

    results = []
    seen = set()

    for block in blocks:
        titolo = clean_title(block.get_text(" ", strip=True))
        if not titolo:
            continue

        link = extract_first_document_link(block, url)
        if not link:
            continue

        key = (titolo, link)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "tipo_atto": "Audizione",
            "titolo": titolo,
            "data_audizione": target_date,
            "link_pdf": link,
            "motivazione_preliminare": "Audizione Camera",
        })

    output_file = OUTPUT_DIR / f"camera_audizioni_{target_date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Trovate audizioni: {len(results)}")
    print(f"Salvato: {output_file}")

    for item in results[:10]:
        print("-", item["titolo"], "|", item["link_pdf"])


if __name__ == "__main__":
    main()