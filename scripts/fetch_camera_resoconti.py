import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.camera.it"
URL = "https://www.camera.it/leg19/207"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_target_date():
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()


def fetch_html():
    r = requests.get(URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def normalize_link(href):
    return urljoin(BASE_URL, href or "")


def compact(text):
    return " ".join((text or "").split()).strip()


def clean_context_text(text: str) -> str:
    text = compact(text)
    text = re.sub(r"\bVai al resoconto\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -|")
    return text


def find_context_container(a_tag: Tag):
    current = a_tag
    for _ in range(6):
        if current is None:
            break
        current = current.parent
        if isinstance(current, Tag):
            txt = compact(current.get_text(" ", strip=True))
            if "Vai al resoconto" in txt and len(txt) > 20:
                return current
    return a_tag.parent


def extract_date(text: str) -> str:
    patterns = [
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4}\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return compact(m.group(0))
    return ""


def extract_seduta(text: str) -> str:
    m = re.search(r"\bseduta\s*n\.?\s*\d+\b", text, flags=re.IGNORECASE)
    if m:
        return compact(m.group(0))
    return ""


def extract_tipo(text: str) -> str:
    text_l = text.lower()
    if "stenograf" in text_l:
        return "Resoconto stenografico"
    if "sommario" in text_l:
        return "Resoconto sommario"
    if "bollettino" in text_l:
        return "Bollettino"
    return "Resoconto"


def build_title(context_text: str, idx: int) -> str:
    text = context_text

    # estrai seduta
    seduta = extract_seduta(text)

    # estrai data leggibile
    data = extract_date(text)

    titolo = "Resoconto Camera"

    if seduta:
        titolo += f" – {seduta}"

    if data:
        titolo += f" – {data}"

    return titolo

def dedupe(items):
    seen = set()
    out = []
    for item in items:
        key = (item["titolo"], item["link_pdf"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def main():
    target_date = get_target_date()

    print("Scarico resoconti Camera (con contesto)...")

    html = fetch_html()
    soup = BeautifulSoup(html, "html.parser")

    items = []

    resoconto_links = []
    for a in soup.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True))
        if "Vai al resoconto" in text:
            resoconto_links.append(a)

    for idx, a in enumerate(resoconto_links, start=1):
        link = normalize_link(a.get("href"))
        container = find_context_container(a)
        context_text = ""
        if isinstance(container, Tag):
            context_text = compact(container.get_text(" ", strip=True))

        context_text = clean_context_text(context_text)

        titolo = build_title(context_text, idx)
        data = extract_date(context_text)
        seduta = extract_seduta(context_text)
        tipo = extract_tipo(context_text)

        items.append({
            "ramo": "Camera",
            "data": target_date,
            "tipo_atto": tipo,
            "titolo": titolo,
            "data_resoconto": data,
            "seduta": seduta,
            "link_pdf": link,
            "categoria_preliminare": "Interesse istituzionale",
            "motivazione_preliminare": "Resoconto Camera",
        })

    items = dedupe(items)

    output_path = OUTPUT_DIR / f"camera_resoconti_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("Trovati:", len(items))
    print("Salvato:", output_path)

    for item in items[:10]:
        print("-", item["tipo_atto"], "|", item["titolo"], "|", item["data_resoconto"], "|", item["seduta"])

if __name__ == "__main__":
    main()