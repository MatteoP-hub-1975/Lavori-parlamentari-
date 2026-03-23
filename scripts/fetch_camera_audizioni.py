import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.camera.it"
URL_TEMPLATE = (
    "https://www.camera.it/leg19/824"
    "?tipo=C&anno={anno}&mese={mese}&giorno={giorno}&view=filtered&pagina=#"
)

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text):
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


def looks_like_audizione(text: str) -> bool:
    t = text.lower()
    return "audizion" in t


def find_context_container(a_tag):
    current = a_tag
    for _ in range(8):
        if current is None:
            break
        current = current.parent
        if current is not None:
            txt = compact(current.get_text(" ", strip=True))
            if len(txt) > 30:
                return current
    return a_tag.parent


def clean_title(text: str) -> str:
    text = compact(text)
    text = re.sub(r"\bscarica pdf\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bresoconto stenografico\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bresoconto sommario\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bvideo\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -|")
    return text


def main():
    target_date = parse_target_date()
    url = build_url(target_date)

    print("Scarico audizioni Camera per data:", target_date)
    print("URL:", url)

    res = requests.get(url, headers=HEADERS, timeout=60)
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
        if not looks_like_audizione(text):
            continue

        full_href = normalize_link(href, url)

        container = find_context_container(a)
        context_text = compact(container.get_text(" ", strip=True)) if container else text
        titolo = clean_title(context_text)

        # prova a catturare un pdf o link documento dallo stesso blocco
        pdf_link = ""
        if container:
            for a2 in container.find_all("a", href=True):
                href2 = normalize_link(a2.get("href", "").strip(), url)
                text2 = compact(a2.get_text(" ", strip=True)).lower()

                if (
                    "documenti.camera.it" in href2.lower()
                    or "getdocumento.ashx" in href2.lower()
                    or "scarica pdf" in text2
                    or href2.lower().endswith(".pdf")
                ):
                    pdf_link = href2
                    break

        # fallback al link dell'audizione trovato
        final_link = pdf_link or full_href

        key = (titolo, final_link)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "tipo_atto": "Audizione",
            "titolo": titolo or text,
            "data_audizione": target_date,
            "link_pdf": final_link,
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