import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.camera.it"
SOURCE_URL = "https://www.camera.it/leg19/167"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ---------------------------
# UTILS
# ---------------------------

def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def normalize_link(href: str) -> str:
    if not href:
        return ""

    if href.startswith("http"):
        return href

    if href.startswith("//"):
        return "https:" + href

    if href.startswith("/"):
        return BASE_URL + href

    return BASE_URL + "/" + href


def is_pdf_link(url: str) -> bool:
    url = (url or "").lower()
    return (
        "getdocumento.ashx" in url
        or url.endswith(".pdf")
    )


# ---------------------------
# DATA LABEL (CHIAVE!)
# ---------------------------

def build_camera_label(target_date: datetime) -> str:
    giorni = [
        "lunedì", "martedì", "mercoledì",
        "giovedì", "venerdì", "sabato", "domenica"
    ]
    mesi = [
        "gennaio", "febbraio", "marzo", "aprile",
        "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"
    ]

    giorno_sett = giorni[target_date.weekday()]
    mese = mesi[target_date.month - 1]

    return f"Documenti stampati {giorno_sett} {target_date.day} {mese} {target_date.year}"


# ---------------------------
# FETCH HTML
# ---------------------------

def fetch_html():
    r = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


# ---------------------------
# FIND TARGET SECTION
# ---------------------------

def find_target_section(soup: BeautifulSoup, label: str):
    for tag in soup.find_all(["strong", "p", "div", "span", "h2", "h3"]):
        text = compact(tag.get_text(" ", strip=True))
        if text.lower() == label.lower():
            return tag
    return None


# ---------------------------
# EXTRACT DOCS + PDF
# ---------------------------

def extract_documents(section_tag: Tag, section_label: str):
    documents = []

    current_doc = None

    for el in section_tag.next_elements:

        if isinstance(el, Tag):
            text = compact(el.get_text(" ", strip=True))

            # STOP quando cambia sezione
            if text.lower().startswith("documenti stampati") and text != section_label:
                break

            # NUOVO DOC
            if re.match(r"^Doc\.\s", text):
                current_doc = {
                    "ramo": "Camera",
                    "tipo_atto": text,
                    "numero": "",
                    "titolo": "",
                    "data": "",
                    "link": "",
                    "commissione": "",
                    "seduta": "",
                    "fonte": "documenti_stampati",
                    "sezione": section_label,
                }
                documents.append(current_doc)
                continue

            # TITOLO
            if current_doc and text and not text.lower().startswith("documenti stampati"):
                if not text.lower().startswith("pdf") and not text.startswith("("):
                    current_doc["titolo"] += " " + text

            # LINK PDF
            if el.name == "a" and el.has_attr("href") and current_doc:
                url = normalize_link(el["href"])

                if is_pdf_link(url) and not current_doc["link"]:
                    current_doc["link"] = url

    # pulizia
    for d in documents:
        d["titolo"] = compact(d["titolo"])

    # solo quelli con link
    return [d for d in documents if d["link"]]


# ---------------------------
# MAIN
# ---------------------------

def main():
    if len(sys.argv) < 2:
        raise ValueError("Serve data YYYY-MM-DD")

    target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d")
    label = build_camera_label(target_date)

    print("Cerco sezione:", label)

    html = fetch_html()
    soup = BeautifulSoup(html, "html.parser")

    section_tag = find_target_section(soup, label)

    if not section_tag:
        print("⚠️ Sezione NON trovata")
        documents = []
    else:
        documents = extract_documents(section_tag, label)

    for d in documents:
        d["data"] = target_date.date().isoformat()

    print("Documenti trovati:", len(documents))

    out = OUTPUT_DIR / f"camera_atti_{target_date.date().isoformat()}.json"

    with open(out, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

    print("Salvato:", out)


if __name__ == "__main__":
    main()