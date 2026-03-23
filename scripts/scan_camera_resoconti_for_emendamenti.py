import json
import re
import sys
from pathlib import Path

import requests
import fitz  # PyMuPDF


OUTPUT_DIR = Path("data/camera")
HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


def load_resoconti(target_date):
    path = OUTPUT_DIR / f"camera_resoconti_{target_date}.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compact(text):
    return " ".join((text or "").split()).strip()


def download_pdf(url):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.content


def extract_pdf_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts = []
    for page in doc:
        parts.append(page.get_text())
    return "\n".join(parts)


def find_snippets(text, patterns, window=180, max_hits=10):
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


def main():
    target_date = parse_target_date()
    items = load_resoconti(target_date)

    patterns = [
        r"\bemendament[oi]\b",
        r"termine\s+per\s+la\s+presentazione\s+degli\s+emendamenti",
        r"presentazione\s+degli\s+emendamenti",
    ]

    results = []

    print("Scansiono resoconti Camera per emendamenti:", target_date)

    for item in items:
        link = item.get("link_pdf", "")
        titolo = item.get("titolo", "")

        if not link:
            continue

        try:
            pdf_bytes = download_pdf(link)
            text = extract_pdf_text(pdf_bytes)

            snippets = find_snippets(text, patterns)

            results.append({
                "titolo": titolo,
                "link_pdf": link,
                "emendamenti_trovati": bool(snippets),
                "snippets": snippets,
            })

            print("-", titolo, "| emendamenti:", bool(snippets), "| hits:", len(snippets))

        except Exception as e:
            results.append({
                "titolo": titolo,
                "link_pdf": link,
                "emendamenti_trovati": False,
                "snippets": [],
                "errore": str(e),
            })
            print("-", titolo, "| errore:", e)

    out = OUTPUT_DIR / f"camera_emendamenti_scan_{target_date}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Salvato:", out)


if __name__ == "__main__":
    main()