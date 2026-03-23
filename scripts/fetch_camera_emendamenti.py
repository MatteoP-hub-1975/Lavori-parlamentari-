import requests
from bs4 import BeautifulSoup

URL = "https://www.camera.it/ricerca-emendamenti/?script=no"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text):
    return " ".join((text or "").split()).strip()


def main():
    print("Test POST emendamenti Camera...")

    payload = {
        "Legislatura": "19",
        "tseduta": "Commissione",
        "ris": "10",
        "hasParams": "true",
        "maxRowsReturned": "10",
        "numPage": "0",
        "numPageEmendamenti": "0",
        "totalPages": "0",
        "totalPagesEmendamenti": "0",
        "numFound": "0",
        "parole": "",
        "nomeDep": "",
        "idAtto": "",
        "art": "",
        "numeme": "",
        "pres": "",
        "esito": "",
        "tpart": "",
        "listaAttiJson": "",
        "attoIndex": "",
        "emendamentoIndex": "",
    }

    r = requests.post(URL, headers=HEADERS, data=payload, timeout=60)
    r.raise_for_status()

    print("STATUS:", r.status_code)

    soup = BeautifulSoup(r.text, "html.parser")
    text = compact(soup.get_text(" ", strip=True))
    print("TESTO INIZIALE:")
    print(text[:2500])

    print("\n=== LINK RISULTATI ===")
    printed = 0
    for a in soup.find_all("a", href=True):
        t = compact(a.get_text(" ", strip=True))
        h = a.get("href", "").strip()
        if not t and not h:
            continue

        print("TEXT:", t)
        print("HREF:", h)
        print("-" * 50)

        printed += 1
        if printed >= 40:
            break


if __name__ == "__main__":
    main()