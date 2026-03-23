import requests
from bs4 import BeautifulSoup

URL = "https://www.camera.it/ricerca-emendamenti/?script=no"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text):
    return " ".join((text or "").split()).strip()


def main():
    print("Scarico pagina emendamenti Camera...")

    r = requests.get(URL, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    form = soup.find("form")
    if not form:
        print("Nessun form trovato")
        return

    target_names = {"tseduta", "Legislatura", "esito", "trp", "pres", "tpart", "ris"}

    for select in form.find_all("select"):
        name = select.get("name")
        if name not in target_names:
            continue

        print(f"\n=== SELECT {name} ===")
        options = select.find_all("option")
        print("Numero opzioni:", len(options))

        for opt in options[:80]:
            print("VALUE:", opt.get("value"), "| TEXT:", compact(opt.get_text(" ", strip=True)))


if __name__ == "__main__":
    main()