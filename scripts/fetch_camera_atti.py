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
    "User-Agent": "Mozilla/5.0 (compatible; CameraMonitor/1.0)"
}


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def normalize_link(href: str) -> str:
    href = (href or "").strip()

    if not href:
        return ""

    if href.startswith("http://") or href.startswith("https://"):
        return href

    if href.startswith("//"):
        return "https:" + href

    if href.startswith("/"):
        return BASE_URL + href

    return BASE_URL + "/" + href.lstrip("/")


def is_useful_document_link(url: str) -> bool:
    url_l = (url or "").lower()

    if not url_l:
        return False

    if "votazioni" in url_l:
        return False

    if "documenti.camera.it" in url_l and "getdocumento.ashx" in url_l:
        return True

    if url_l.endswith(".pdf"):
        return True

    return False


def find_first_documenti_stampati_header(soup: BeautifulSoup):
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "strong", "p", "div", "span"]):
        text = compact_spaces(tag.get_text(" ", strip=True))
        if text.lower().startswith("documenti stampati "):
            return tag, text
    return None, ""


def extract_doc_blocks_from_text(first_section_text: str, section_label: str):
    lines = [compact_spaces(x) for x in first_section_text.splitlines()]
    lines = [x for x in lines if x]

    documents = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if re.match(r"^Doc\.\s", line):
            tipo_num = line
            titolo_parts = []

            j = i + 1
            while j < len(lines):
                next_line = lines[j]

                if next_line.lower().startswith("documenti stampati "):
                    break
                if re.match(r"^Doc\.\s", next_line):
                    break
                if next_line.lower() in {"[pdf]", "pdf"}:
                    break
                if re.match(r"^\(\d+\s*kb\)$", next_line.lower()):
                    break

                titolo_parts.append(next_line)
                j += 1

            titolo = compact_spaces(" ".join(titolo_parts))

            m = re.match(r"^(Doc\.\s*[A-Z0-9.\-–—]+)", tipo_num, flags=re.IGNORECASE)
            tipo_atto = compact_spaces(m.group(1)) if m else tipo_num

            numero = ""
            m_num = re.search(r"\bn\.\s*([0-9]+)\b", titolo, flags=re.IGNORECASE)
            if m_num:
                numero = m_num.group(1)

            documents.append(
                {
                    "ramo": "Camera",
                    "tipo_atto": tipo_atto,
                    "numero": numero,
                    "titolo": titolo,
                    "data": "",
                    "link": "",
                    "commissione": "",
                    "seduta": "",
                    "fonte": "documenti_stampati",
                    "sezione": section_label,
                }
            )

            i = j
            continue

        i += 1

    return documents


def extract_links_from_first_section(header_tag: Tag):
    links = []

    for el in header_tag.next_elements:
        if isinstance(el, Tag):
            text = compact_spaces(el.get_text(" ", strip=True)).lower()
            if text.startswith("documenti stampati ") and el is not header_tag:
                break

            if el.name == "a" and el.has_attr("href"):
                url = normalize_link(el["href"])
                if is_useful_document_link(url):
                    links.append(url)

    seen = set()
    deduped = []
    for x in links:
        if x not in seen:
            seen.add(x)
            deduped.append(x)

    return deduped


def extract_documents(html: str):
    soup = BeautifulSoup(html, "html.parser")

    header_tag, section_label = find_first_documenti_stampati_header(soup)
    if not header_tag:
        return []

    # testo solo della prima sezione
    section_parts = [section_label]

    for el in header_tag.next_elements:
        if isinstance(el, Tag):
            text = compact_spaces(el.get_text(" ", strip=True))
            if text.lower().startswith("documenti stampati ") and text != section_label:
                break

            if text:
                section_parts.append(text)

    first_section_text = "\n".join(section_parts)
    documents = extract_doc_blocks_from_text(first_section_text, section_label)
    links = extract_links_from_first_section(header_tag)

    # abbina in ordine, ma usando solo link utili della stessa sezione
    for idx, doc in enumerate(documents):
        if idx < len(links):
            doc["link"] = links[idx]

    documents = [x for x in documents if x.get("link")]
    return documents


def save_json(items, target_date_str):
    output_path = OUTPUT_DIR / f"camera_atti_{target_date_str}.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    return output_path


def main():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")

    target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    target_date_str = target_date.isoformat()

    print("Scarico ultimi documenti stampati della Camera")

    html = fetch_html(SOURCE_URL)
    documents = extract_documents(html)

    for item in documents:
        item["data"] = target_date_str

    print(f"Documenti trovati: {len(documents)}")

    output_path = save_json(documents, target_date_str)

    print(f"File salvato in: {output_path}")


if __name__ == "__main__":
    main()