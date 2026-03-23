import requests
from bs4 import BeautifulSoup

URL = "https://documenti.camera.it/apps/commonServices/getDocumento.ashx?sezione=commissioni&tipoDoc=elencoResoconti&idLegislatura=19&tipoElenco=audizioniCronologico&calendario=false&audiz=160305&scheda=true"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text):
    return " ".join((text or "").split()).strip()


def main():
    print("Scarico scheda audizione...")

    res = requests.get(URL, headers=HEADERS, timeout=60)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    text = compact(soup.get_text(" ", strip=True))

    print(text[:4000])


if __name__ == "__main__":
    main()