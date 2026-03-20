import requests
from bs4 import BeautifulSoup

URLS = [
    "https://www.camera.it/leg19/410?tipo=alfabetico_stenografico",
    "https://www.camera.it/leg19/410?tipo=sommario",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text):
    return " ".join((text or "").split()).strip()


for url in URLS:
    print("\n" + "=" * 80)
    print("URL:", url)
    print("=" * 80)

    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    found = 0
    for a in soup.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not text and not href:
            continue

        print("TEXT:", text)
        print("HREF:", href)
        print("-" * 40)

        found += 1
        if found >= 40:
            break

    print("Link stampati:", found)