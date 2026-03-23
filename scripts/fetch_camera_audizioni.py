import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


URL = "https://www.camera.it/leg19/546?tipo=elencoAudizioni"
BASE_URL = "https://www.camera.it"
OUTPUT_DIR = Path("data/camera")
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


def compact(text):
    return " ".join((text or "").split()).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


def parse_it_date(text: str) -> str:
    text = compact(text).lower()
    m = re.search(
        r"\b(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)?\s*(\d{1,2})\s+"
        r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+"
        r"(\d{4})\b",
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


def find_context_container(a_tag: Tag):
    current = a_tag
    for _ in range(8):
        if current is None:
            break
        current = current.parent
        if isinstance(current, Tag):
            txt = compact(current.get_text(" ", strip=True))
            if len(txt) > 30:
                return current
    return a_tag.parent


def main():
    target_date = parse_target_date()

    print("Scarico audizioni Camera per data:", target_date)

    res = requests.get(URL, headers=HEADERS, timeout=60)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    links = soup.find_all("a", href=True)

    results = []
    seen = set()

    for a in links:
        text = compact(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not text or not href:
            continue
        if "audizion" not in text.lower():
            continue

        full_href = urljoin(BASE_URL, href)
        if "audiz=" not in full_href:
            continue

        container = find_context_container(a)
        context_text = compact(container.get_text(" ", strip=True)) if container else text
        data_iso = parse_it_date(context_text)

        if data_iso != target_date:
            continue

        key = (text, full_href)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "tipo_atto": "Audizione",
            "titolo": text,
            "data_audizione": data_iso,
            "link_pdf": full_href,
            "motivazione_preliminare": "Audizione Camera",
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"camera_audizioni_{target_date}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Trovate audizioni: {len(results)}")
    print(f"Salvato: {output_file}")

    for item in results[:10]:
        print("-", item["data_audizione"], "|", item["titolo"], "|", item["link_pdf"])


if __name__ == "__main__":
    main()