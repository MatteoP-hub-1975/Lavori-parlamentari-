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

    # cerca il contenitore principale del sommario
    content = soup.find("div", {"class": "container"})

    if not content:
        return atti

    # prendi solo i paragrafi (gli atti sono spesso lì)
    for p in content.find_all("p"):
        text = p.get_text(" ", strip=True)

        if not text:
            continue

        # filtro minimo per evitare roba inutile
        if len(text) < 30:
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