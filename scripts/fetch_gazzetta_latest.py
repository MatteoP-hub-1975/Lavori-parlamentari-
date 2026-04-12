import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://www.gazzettaufficiale.it"

SOURCES = {
    "serie_generale": {
        "label": "Serie Generale",
        "list_url": "https://www.gazzettaufficiale.it/30giorni/serie_generale",
        "detail_path": "/gazzetta/serie_generale/caricaDettaglio/home",
    },
    "unione_europea": {
        "label": "2ª Serie Speciale - Unione Europea",
        "list_url": "https://www.gazzettaufficiale.it/30giorni/unione_europea",
        "detail_path": "/gazzetta/unione_europea/caricaDettaglio/home",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ConfitarmaMonitor/1.0)"
}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_latest_issue(list_url: str, detail_path: str, series_label: str) -> dict:
    html = fetch_html(list_url)
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n", strip=True)

    # Cerca tutte le occorrenze tipo: n° 84 del 11-04-2026
    matches = re.findall(r"n°\s*(\d+)\s+del\s+(\d{2}-\d{2}-\d{4})", text)

    if not matches:
        raise ValueError(f"Nessuna gazzetta trovata in {list_url}")

    numero, data_pub = matches[-1]  # l'ultima presente nella lista

    # converte data da DD-MM-YYYY a YYYY-MM-DD
    dd, mm, yyyy = data_pub.split("-")
    iso_date = f"{yyyy}-{mm}-{dd}"

    detail_url = (
        f"{BASE_URL}{detail_path}"
        f"?dataPubblicazioneGazzetta={iso_date}&numeroGazzetta={numero}"
    )

    pdf_url = None
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text_link = link.get_text(" ", strip=True)

        if f"n° {numero} del {data_pub}" in text_link:
            break

    # prova a ricavare il PDF dal link "Download PDF" vicino all'ultima occorrenza
    all_links = soup.find_all("a", href=True)
    for i, link in enumerate(all_links):
        text_link = link.get_text(" ", strip=True)
        if f"n° {numero} del {data_pub}" in text_link:
            # cerca indietro il primo link "Download PDF"
            for j in range(max(0, i - 5), i):
                prev_text = all_links[j].get_text(" ", strip=True)
                if "Download PDF" in prev_text:
                    pdf_url = urljoin(BASE_URL, all_links[j]["href"])
            break

    return {
        "series_key": series_label,
        "numero_gazzetta": numero,
        "data_pubblicazione": iso_date,
        "detail_url": detail_url,
        "pdf_url": pdf_url,
        "source_url": list_url,
    }


def main():
    results = {}

    for key, config in SOURCES.items():
        results[key] = extract_latest_issue(
            list_url=config["list_url"],
            detail_path=config["detail_path"],
            series_label=config["label"],
        )

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()