import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.senato.it"
OUTPUT_DIR = Path("data/senato")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SenatoMonitor/1.0)"
}

TIMEOUT = 60
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 3


def compact_spaces(text: str) -> str:
    return " ".join((text or "").split()).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data nel formato YYYY-MM-DD")
    return datetime.strptime(sys.argv[1], "%Y-%m-%d").date()


def build_day_url(target_date) -> str:
    ymd = target_date.strftime("%Y%m%d")
    return f"{BASE_URL}/leggi-e-documenti/ultimi-atti-pubblicati/periodo?from={ymd}&to={ymd}"


def fetch_html(url: str) -> str:
    last_response = None
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            last_response = response

            if response.status_code == 200:
                return response.text

            if response.status_code in {500, 502, 503, 504}:
                print(
                    f"Tentativo {attempt}/{MAX_RETRIES}: server Senato ha risposto "
                    f"{response.status_code}. Ritento tra {RETRY_WAIT_SECONDS} secondi..."
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_WAIT_SECONDS)
                    continue

                print(
                    f"Server Senato ancora in errore ({response.status_code}) "
                    "dopo i retry. Tratto il giorno come senza atti disponibili."
                )
                return ""

            response.raise_for_status()

        except requests.RequestException as e:
            last_error = e
            print(
                f"Tentativo {attempt}/{MAX_RETRIES}: errore HTTP/rete: {e}. "
                f"Ritento tra {RETRY_WAIT_SECONDS} secondi..."
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SECONDS)
                continue

    if last_response is not None:
        last_response.raise_for_status()

    if last_error is not None:
        raise last_error

    return ""


def parse_html(html: str):
    if not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if "/service/PDF/PDFServer/" not in href:
            continue

        full_link = href if href.startswith("http") else f"{BASE_URL}{href}"
        text = compact_spaces(link.get_text(" ", strip=True))

        parent_text = ""
        parent = link.parent
        if parent is not None:
            parent_text = compact_spaces(parent.get_text(" ", strip=True))

        grandparent_text = ""
        if parent is not None and parent.parent is not None:
            grandparent_text = compact_spaces(parent.parent.get_text(" ", strip=True))

        combined_title = text
        if not combined_title:
            combined_title = parent_text
        if not combined_title:
            combined_title = grandparent_text
        if not combined_title:
            combined_title = "pdf"

        items.append(
            {
                "ramo": "Senato",
                "tipo_atto": "Documento",
                "numero": "",
                "titolo": combined_title,
                "data": "",
                "link": full_link,
                "commissione": "",
                "seduta": "",
            }
        )

    dedup = []
    seen = set()

    for item in items:
        key = item["link"]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)

    return dedup


def save_json(items, target_date_str: str) -> Path:
    output_path = OUTPUT_DIR / f"senato_atti_{target_date_str}.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return output_path


def main():
    target_date = parse_target_date()
    target_date_str = target_date.isoformat()

    page_url = build_day_url(target_date)

    print(f"Recupero atti Senato del giorno {target_date_str}")
    print(f"URL: {page_url}")

    html = fetch_html(page_url)
    items = parse_html(html)

    for item in items:
        item["data"] = target_date_str

    output_path = save_json(items, target_date_str)

    print(f"Atti trovati: {len(items)}")
    print(f"File salvato in: {output_path}")


if __name__ == "__main__":
    main()