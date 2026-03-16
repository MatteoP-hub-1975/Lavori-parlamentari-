import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


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
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href.lstrip("/")


def extract_documents(html: str):
    soup = BeautifulSoup(html, "html.parser")
    lines = [compact_spaces(x) for x in soup.get_text("\n", strip=True).splitlines()]
    lines = [x for x in lines if x]

    pdf_links = []
    for a in soup.find_all("a", href=True):
        label = compact_spaces(a.get_text(" ", strip=True)).lower()
        href = a["href"]
        full = normalize_link(href)

        if "[pdf]" in label or label == "pdf" or "documenti.camera.it" in full.lower():
            pdf_links.append(full)

    seen = set()
    pdf_links = [x for x in pdf_links if not (x in seen or seen.add(x))]

    documents = []
    current_date_label = ""

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.lower().startswith("documenti stampati "):
            current_date_label = line
            i += 1
            continue

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

            tipo_atto = ""
            numero = ""

            m = re.match(r"^(Doc\.\s*[A-Z0-9.\-–—]+)", tipo_num, flags=re.IGNORECASE)
            if m:
                tipo_atto = compact_spaces(m.group(1))
            else:
                tipo_atto = tipo_num

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
                    "sezione": current_date_label,
                }
            )

            i = j
            continue

        i += 1

    for idx, doc in enumerate(documents):
        if idx < len(pdf_links):
            doc["link"] = pdf_links[idx]

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