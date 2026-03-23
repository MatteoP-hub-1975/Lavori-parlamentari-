import requests
from bs4 import BeautifulSoup
import sys

HEADERS = {"User-Agent": "Mozilla/5.0"}

URL_TEMPLATE = (
    "https://www.camera.it/leg19/824"
    "?tipo=C&anno={anno}&mese={mese}&giorno={giorno}&view=filtered&pagina=#"
)

def compact(text):
    return " ".join((text or "").split()).strip()

def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]

def build_url(target_date: str) -> str:
    anno, mese, giorno = target_date.split("-")
    return URL_TEMPLATE.format(anno=anno, mese=mese, giorno=giorno)

def main():
    target_date = parse_target_date()
    url = build_url(target_date)

    print("Scarico audizioni Camera per data:", target_date)
    print("URL:", url)

    res = requests.get(url, headers=HEADERS, timeout=60)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    printed = 0
    for tag in soup.find_all(["div", "li", "p", "td", "section", "article", "a"]):
        text = compact(tag.get_text(" ", strip=True))
        if not text:
            continue
        if "audizion" not in text.lower():
            continue

        print("TAG:", tag.name)
        print("TEXT:", text[:1000])
        print("-" * 80)

        printed += 1
        if printed >= 20:
            break

    print("Blocchi con 'audizion' trovati:", printed)

if __name__ == "__main__":
    main()