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

    print("TITLE:", compact(soup.title.get_text(" ", strip=True)) if soup.title else "")

    print("\n=== LINK ===")
    count = 0
    for a in soup.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()
        if text or href:
            print("TEXT:", text)
            print("HREF:", href)
            print("-" * 40)
            count += 1
            if count >= 40:
                break

    print("\n=== IFRAME ===")
    for iframe in soup.find_all("iframe"):
        print(iframe.get("src", ""))

    print("\n=== SCRIPT SRC ===")
    for script in soup.find_all("script", src=True):
        print(script.get("src", ""))


if __name__ == "__main__":
    main()