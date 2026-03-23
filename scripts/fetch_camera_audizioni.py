import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://www.camera.it/leg19/546?tipo=elencoAudizioni"
BASE_URL = "https://www.camera.it"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text):
    return " ".join((text or "").split()).strip()


def main():
    print("Scarico pagina audizioni Camera...")

    res = requests.get(URL, headers=HEADERS, timeout=60)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    links = soup.find_all("a", href=True)

    print(f"Link totali trovati: {len(links)}\n")

    printed = 0
    for a in links:
        text = compact(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()
        full_href = urljoin(BASE_URL, href)

        combined = f"{text} {full_href}".lower()

        if not any(x in combined for x in [
            "audizion",
            "documenti.camera.it",
            "getdocumento.ashx",
            "resoconto stenografico",
        ]):
            continue

        print("TEXT:", text)
        print("HREF:", full_href)
        print("-" * 60)

        printed += 1
        if printed >= 60:
            break

    print("\nLink utili stampati:", printed)


if __name__ == "__main__":
    main()