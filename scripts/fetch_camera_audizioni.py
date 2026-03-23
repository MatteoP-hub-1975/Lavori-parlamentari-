import requests
from bs4 import BeautifulSoup

URL = "https://www.camera.it/leg19/546?tipo=elencoAudizioni"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text):
    return " ".join((text or "").split()).strip()


def main():
    print("Scarico pagina audizioni Camera...")

    res = requests.get(URL, headers=HEADERS, timeout=60)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    links = soup.find_all("a", href=True)

    print(f"Link trovati: {len(links)}\n")

    printed = 0
    for a in links:
        text = compact(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not text or not href:
            continue

        print("TEXT:", text)
        print("HREF:", href)
        print("-" * 40)

        printed += 1
        if printed >= 80:
            break


if __name__ == "__main__":
    main()