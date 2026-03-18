import json
import sys
from datetime import datetime
from pathlib import Path


INPUT_DIR = Path("data/camera")
OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def compact(text):
    if text is None:
        return ""
    return str(text).strip()


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
            "tipo_atto": compact(item.get("tipo_atto")),
            "numero": compact(item.get("numero")),
            "titolo": compact(item.get("titolo")),
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