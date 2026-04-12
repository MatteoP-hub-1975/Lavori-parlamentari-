import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ConfitarmaMonitor/1.0)"
}


def fetch_html(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_gazzetta_detail(detail_url):
    html = fetch_html(detail_url)
    soup = BeautifulSoup(html, "html.parser")

    atti = []

    # Gli atti veri sono nei link <a> centrali della pagina
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)

        if not text:
            continue

        # filtro: gli atti hanno sempre testo abbastanza lungo
        if len(text) < 40:
            continue

        # filtro: devono contenere parole tipiche normative
        keywords = [
            "DECRETO",
            "LEGGE",
            "DELIBERA",
            "ORDINANZA",
            "COMUNICATO",
            "REGOLAMENTO",
            "DETERMINA"
        ]

        if not any(k in text.upper() for k in keywords):
            continue

        atti.append({
            "raw_text": text
        })

    return atti