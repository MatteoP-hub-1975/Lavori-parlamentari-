import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.senato.it"
OUTPUT_DIR = Path("data/senato")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SenatoMonitor/1.0)"
}


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data nel formato YYYY-MM-DD")
    return datetime.strptime(sys.argv[1], "%Y-%m-%d").date()


def build_day_url(target_date) -> str:
    ymd = target_date.strftime("%Y%m%d")
    return f"{BASE_URL}/leggi-e-documenti/ultimi-atti-pubblicati/periodo?from={ymd}&to={ymd}"


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def extract_entries(page_url: str, html: str, target_date: str):
    soup = BeautifulSoup(html, "html.parser")

    entries = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(page_url, href)

        if "/PDF/" not in full_url:
            continue

        if full_url in seen_links:
            continue

        seen_links.add(full_url)

        parent = a.parent
        parent_text = compact_spaces(parent.get_text(" ", strip=True)) if parent else ""
        context_text = parent_text or compact_spaces(a.get_text(" ", strip=True))

        tipo_atto = "Documento"
        numero = ""
        titolo = context_text
        commissione = ""
        seduta = ""

        m_ddl = re.search(r"Disegno di legge\s+(\d+)", context_text, flags=re.IGNORECASE)
        if m_ddl:
            tipo_atto = "DDL"
            numero = m_ddl.group(1)
        elif re.search(r"O\.D\.G\.|Ordine del giorno", context_text, flags=re.IGNORECASE):
            tipo_atto = "ODG"
            m_seduta = re.search(r"seduta(?:/e)?\s*n\.\s*([0-9]+)", context_text, flags=re.IGNORECASE)
            if m_seduta:
                seduta = m_seduta.group(1)
                numero = seduta
        elif re.search(r"Risposte scritte", context_text, flags=re.IGNORECASE):
            tipo_atto = "Risposte scritte"

        entries.append(
            {
                "ramo": "Senato",
                "tipo_atto": tipo_atto,
                "numero": numero,
                "titolo": titolo,
                "data": target_date,
                "link": full_url,
                "commissione": commissione,
                "seduta": seduta,
            }
        )

    return entries


def save_json(entries, target_date: str):
    output_path = OUTPUT_DIR / f"senato_atti_{target_date}.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return output_path


def main():
    target_date = parse_target_date()
    target_date_str = target_date.isoformat()

    page_url = build_day_url(target_date)
    print(f"Recupero atti Senato del giorno {target_date_str}")
    print(f"URL: {page_url}")

    html = fetch_html(page_url)
    entries = extract_entries(page_url, html, target_date_str)

    output_path = save_json(entries, target_date_str)

    print(f"Atti trovati: {len(entries)}")
    print(f"File salvato in: {output_path}")


if __name__ == "__main__":
    main()
