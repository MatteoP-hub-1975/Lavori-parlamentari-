import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.camera.it"
URL_TEMPLATE = "https://www.camera.it/leg19/187?slAnnoMese={yyyymm}&slGiorno={day}&idSeduta="

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/pdf,*/*",
}


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.today() - timedelta(days=1)).date().isoformat()


def build_odg_url(target_date: str) -> str:
    year, month, day = target_date.split("-")
    return URL_TEMPLATE.format(yyyymm=f"{year}{month}", day=day)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r.text


def find_snippets(text: str, patterns, window=220, max_hits=8):
    hits = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            start = max(0, m.start() - window)
            end = min(len(text), m.end() + window)
            snippet = compact(text[start:end])
            if snippet and snippet not in hits:
                hits.append(snippet)
            if len(hits) >= max_hits:
                return hits
    return hits


def extract_fascicolo_link(soup: BeautifulSoup, base_url: str) -> str:
    for a in soup.find_all("a", href=True):
        text = compact(a.get_text(" ", strip=True))
        if "Fascicolo ODG" in text:
            return urljoin(base_url, a["href"])
    return ""


def extract_title_and_date(text: str):
    seduta = ""
    data_line = ""

    m_seduta = re.search(r"\b(\d+)\^?\s+SEDUTA PUBBLICA\b", text, flags=re.IGNORECASE)
    if m_seduta:
        seduta = f"Seduta n. {m_seduta.group(1)}"

    m_data = re.search(
        r"\b(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)\s+\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4}\b",
        text,
        flags=re.IGNORECASE,
    )
    if m_data:
        data_line = compact(m_data.group(0))

    title = "ODG Assemblea"
    if seduta:
        title += f" – {seduta}"
    if data_line:
        title += f" – {data_line}"

    return title, seduta, data_line


def main():
    target_date = get_target_date()
    url = build_odg_url(target_date)

    print("Scansiono ODG Camera per alert:", target_date)
    print("URL:", url)

    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    full_text = compact(soup.get_text(" ", strip=True))

    title, seduta, data_line = extract_title_and_date(full_text)
    fascicolo_link = extract_fascicolo_link(soup, url)

    audizioni_patterns = [
        r"\baudizion[ei]\b",
        r"\baudizione\b",
        r"\baudizioni\b",
    ]

    emendamenti_patterns = [
        r"termine\s+per\s+la\s+presentazione\s+degli\s+emendamenti",
        r"presentazione\s+degli\s+emendamenti",
        r"\bemendament[oi]\b",
    ]

    audizioni_snippets = find_snippets(full_text, audizioni_patterns)
    emendamenti_snippets = find_snippets(full_text, emendamenti_patterns)

    result = {
        "target_date": target_date,
        "url": url,
        "titolo": title,
        "seduta": seduta,
        "data_odg": data_line,
        "fascicolo_odg": fascicolo_link,
        "audizioni_presenti": bool(audizioni_snippets),
        "emendamenti_presenti": bool(emendamenti_snippets),
        "audizioni_snippets": audizioni_snippets,
        "emendamenti_snippets": emendamenti_snippets,
    }

    out_path = OUTPUT_DIR / f"camera_odg_alerts_{target_date}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Salvato:", out_path)
    print("Audizioni presenti:", result["audizioni_presenti"], "| hits:", len(audizioni_snippets))
    print("Emendamenti presenti:", result["emendamenti_presenti"], "| hits:", len(emendamenti_snippets))
    if fascicolo_link:
        print("Fascicolo ODG:", fascicolo_link)


if __name__ == "__main__":
    main()