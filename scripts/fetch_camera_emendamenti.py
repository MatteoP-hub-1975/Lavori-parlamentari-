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

    print("TITLE:", compact(soup.title.get_text(" ", strip=True)) if soup.title else "")

    print("\n=== FORM ===")
    forms = soup.find_all("form")
    print("Numero form:", len(forms))

    for i, form in enumerate(forms, start=1):
        print(f"\n--- FORM {i} ---")
        print("ACTION:", form.get("action"))
        print("METHOD:", form.get("method"))

        for inp in form.find_all(["input", "select", "textarea"]):
            print(
                "TAG:", inp.name,
                "| NAME:", inp.get("name"),
                "| TYPE:", inp.get("type"),
                "| VALUE:", inp.get("value")
            )

if __name__ == "__main__":
    main()