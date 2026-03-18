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

    text = re.sub(r":([A-Za-zÀ-ÖØ-öø-ÿ])", r": \1", text)
    text = re.sub(r"([a-zàèéìòù])([A-ZÀ-ÖØ-Þ])", r"\1 \2", text)
    text = re.sub(r"([A-ZÀ-ÖØ-Þ]{2,})([A-ZÀ-ÖØ-Þ][a-zàèéìòù])", r"\1 \2", text)

    text = re.sub(r"(atto)(Relatrice)", r"\1 \2", text)
    text = re.sub(r"(Presidenza)(il)", r"\1 \2", text)

    text = re.sub(r"\[PDF\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*\d+\s*kb\s*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_tipo_atto(text):
    text = compact(text)

    # inserisce spazio prima di "n." solo quando manca
    # es: "Doc. XCIIIn. 3" -> "Doc. XCIII n. 3"
    text = re.sub(r"(?<=\S)(n\.\s*\d+)", r" \1", text)

    # sistema il caso "bisn. 5" -> "bis n. 5"
    text = re.sub(r"(bis)(n\.\s*\d+)", r"\1 \2", text, flags=re.IGNORECASE)

    # normalizza spazi
    text = re.sub(r"\s+", " ", text).strip()

    return text

def parse_title_fields(text):
    text = clean_text(text)

    patterns = [
        r"\bRelatrice:\s*",
        r"\bRelatore:\s*",
        r"\bPresentata dal\b",
        r"\bPresentato dal\b",
        r"\bPresentata dalla\b",
        r"\bPresentato dalla\b",
        r"\bTrasmessa alla Presidenza\b",
        r"\bTrasmesso alla Presidenza\b",
        r"\bComunicato alla Presidenza\b",
        r"\bApprovato\b",
    ]

    first_idx = len(text)
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m and m.start() < first_idx:
            first_idx = m.start()

    titolo = text[:first_idx].strip() if first_idx < len(text) else text.strip()
    resto = text[first_idx:].strip() if first_idx < len(text) else ""

    titolo = re.sub(r"^(bis)\s+", "", titolo, flags=re.IGNORECASE).strip()

    relatrice = ""
    presentazione = ""
    trasmissione = ""
    comunicazione = ""
    approvazione = ""
    altri = []

    if resto:
        split_points = []
        for pat in patterns:
            for m in re.finditer(pat, resto, flags=re.IGNORECASE):
                split_points.append((m.start(), m.group(0)))

        split_points = sorted(split_points, key=lambda x: x[0])

        chunks = []
        for idx, (start, marker) in enumerate(split_points):
            end = split_points[idx + 1][0] if idx + 1 < len(split_points) else len(resto)
            chunk = resto[start:end].strip()
            if chunk:
                chunks.append(chunk)

        for chunk in chunks:
            lower = chunk.lower()
            if lower.startswith("relatrice:") or lower.startswith("relatore:"):
                relatrice = chunk
            elif lower.startswith("presentata") or lower.startswith("presentato"):
                presentazione = chunk
            elif lower.startswith("trasmessa") or lower.startswith("trasmesso"):
                trasmissione = chunk
            elif lower.startswith("comunicato"):
                comunicazione = chunk
            elif lower.startswith("approvato"):
                approvazione = chunk
            else:
                altri.append(chunk)

    return {
        "titolo": titolo,
        "relatrice": relatrice,
        "presentazione": presentazione,
        "trasmissione": trasmissione,
        "comunicazione": comunicazione,
        "approvazione": approvazione,
        "altri_dettagli": " | ".join(altri),
    }


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
        tipo = clean_tipo_atto(item.get("tipo_atto", ""))
        parsed = parse_title_fields(item.get("titolo", ""))

        normalized_item = {
            "ramo": "Camera",
            "data_pubblicazione": target_date_str,
            "sezione": compact(item.get("sezione")),
            "tipo_atto": tipo,
            "numero": compact(item.get("numero")),
            "titolo": parsed["titolo"],
            "relatrice": parsed["relatrice"],
            "presentazione": parsed["presentazione"],
            "trasmissione": parsed["trasmissione"],
            "comunicazione": parsed["comunicazione"],
            "approvazione": parsed["approvazione"],
            "altri_dettagli": parsed["altri_dettagli"],
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