import json
import sys
import re
from datetime import datetime
from pathlib import Path


INPUT_DIR = Path("data/camera")
OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def compact(text):
    if text is None:
        return ""
    return str(text).strip()


def clean_text(text):
    if not text:
        return ""

    text = str(text)

    # spazio dopo i due punti
    text = re.sub(r":([A-Za-zÀ-ÖØ-öø-ÿ])", r": \1", text)

    # spazio tra minuscola e maiuscola
    text = re.sub(r"([a-zàèéìòù])([A-ZÀ-ÖØ-Þ])", r"\1 \2", text)

    # fix ricorrenti Camera
    text = re.sub(r"(atto)(Relatrice)", r"\1 \2", text)
    text = re.sub(r"(Presidenza)(il)", r"\1 \2", text)

    # normalizza spazi
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_tipo_atto(text):
    text = clean_text(text)

    # Doc. XCIIIn. 3 -> Doc. XCIII n. 3
    text = re.sub(r"(?<!\s)(n\.\s*\d+)", r" \1", text)

    # Doc. XXII-bisn. 5 -> Doc. XXII-bis n. 5
    text = re.sub(r"(bis)(n\.\s*\d+)", r"\1 \2", text)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_title(text):
    text = clean_text(text)

    # rimuove residui tipo [PDF], (123 kb)
    text = re.sub(r"\[PDF\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*\d+\s*kb\s*\)", "", text, flags=re.IGNORECASE)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return datetime.strptime(sys.argv[1], "%Y-%m-%d").date()


def load_raw(target_date_str):
    path = INPUT_DIR / f"camera_atti_{target_date_str}.json"

    if not path.exists():
        print("File input non trovato:", path)
        return []

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_items(items, target_date_str):
    normalized = []

    for item in items:
        normalized_item = {
            "ramo": "Camera",
            "data_pubblicazione": target_date_str,
            "sezione": compact(item.get("sezione")),
            "tipo_atto": clean_tipo_atto(item.get("tipo_atto")),
            "numero": compact(item.get("numero")),
            "titolo": clean_title(item.get("titolo")),
            "commissione": "",
            "seduta": "",
            "link_pdf": compact(item.get("link")),
            "categoria_preliminare": "Non attinenti",
            "motivazione_preliminare": "Documento stampato Camera",
            "richiede_lettura_pdf": True
        }

        normalized.append(normalized_item)

    return normalized


def save_json(items, target_date_str):
    path = OUTPUT_DIR / f"camera_atti_strutturati_{target_date_str}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    return path


def main():
    target_date = parse_target_date()
    target_date_str = target_date.isoformat()

    raw_items = load_raw(target_date_str)

    if not raw_items:
        print("Nessun atto trovato per questa data.")
        output = save_json([], target_date_str)
        print("File salvato in:", output)
        return

    normalized = normalize_items(raw_items, target_date_str)

    output = save_json(normalized, target_date_str)

    print("Atti strutturati:", len(normalized))
    print("File salvato in:", output)


if __name__ == "__main__":
    main()