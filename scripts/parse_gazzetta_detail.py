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

    # La GU struttura il sommario spesso in <li>
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)

        # filtro minimo per evitare rumore
        if len(text) < 20:
            continue

        atti.append({
            "raw_text": text
        })

    return atti


def main():
    # TEST manuale – metti qui uno dei tuoi URL
    url = "INSERISCI_QUI_DETAIL_URL"

    atti = parse_gazzetta_detail(url)

    for a in atti:
        print(a["raw_text"])


if __name__ == "__main__":
    main()