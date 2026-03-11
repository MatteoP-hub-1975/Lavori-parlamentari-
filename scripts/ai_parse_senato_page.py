import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from openai import OpenAI


BASE_URL = "https://www.senato.it"
OUTPUT_DIR = Path("data/senato")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SenatoMonitor/1.0)"
}

EXCLUDED_ORGANS = [
    "Giunta Regolamento",
    "Giunta elezioni e immunità parlamentari",
    "Giunta provvisoria per la verifica dei poteri",
    "Commissione biblioteca e archivio storico",
    "Commissione straordinaria per il contrasto dei fenomeni di intolleranza, razzismo, antisemitismo e istigazione all'odio e alla violenza",
    "Commissione straordinaria per la tutela e la promozione dei diritti umani",
    "Commissione di inchiesta su scomparsa Orlandi e Gregori",
    "Commissione contenziosa",
    "Consiglio di garanzia",
    "Comitato per la legislazione",
]


def is_excluded_organ(item) -> bool:
    searchable_text = " ".join(
        [
            str(item.get("commissione", "")),
            str(item.get("titolo", "")),
            str(item.get("tipo_atto", "")),
            str(item.get("sezione", "")),
            str(item.get("numero", "")),
        ]
    ).lower()

    for organ in EXCLUDED_ORGANS:
        if organ.lower() in searchable_text:
            return True

    return False


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data nel formato YYYY-MM-DD")
    return datetime.strptime(sys.argv[1], "%Y-%m-%d").date()


def build_day_url(target_date) -> str:
    ymd = target_date.strftime("%Y%m%d")
    return f"{BASE_URL}/leggi-e-documenti/ultimi-atti-pubblicati/periodo?from={ymd}&to={ymd}"


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def extract_page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [compact_spaces(x) for x in text.splitlines()]
    lines = [x for x in lines if x]
    return "\n".join(lines)


def build_prompt(target_date_str: str, page_url: str, page_text: str, raw_entries_json: str) -> str:
    return f"""
Analizza la seguente pagina del Senato italiano "Ultimi atti pubblicati" relativa alla data {target_date_str}.

URL della pagina:
{page_url}

Testo della pagina:
<<<BEGIN_PAGE_TEXT>>>
{page_text}
<<<END_PAGE_TEXT>>>

ELENCO DEI PDF TROVATI DALLO SCRAPER:
<<<BEGIN_PDF_LIST>>>
{raw_entries_json}
<<<END_PDF_LIST>>>

Obiettivo:
1. Individuare i singoli atti/documenti pubblicati quel giorno.
2. Restituire una lista JSON di atti strutturati.
3. Associare il link_pdf più plausibile tra quelli forniti.
4. Non riportare nell'output gli organi esclusi.

Regola di esclusione assoluta:
Se un atto riguarda uno dei seguenti organi del Senato, non devi classificarlo né restituirlo nell'output JSON. Devi semplicemente ometterlo del tutto.

Organi da escludere:
- Giunta Regolamento
- Giunta elezioni e immunità parlamentari
- Giunta provvisoria per la verifica dei poteri
- Commissione biblioteca e archivio storico
- Commissione straordinaria per il contrasto dei fenomeni di intolleranza, razzismo, antisemitismo e istigazione all'odio e alla violenza
- Commissione straordinaria per la tutela e la promozione dei diritti umani
- Commissione di inchiesta su scomparsa Orlandi e Gregori
- Commissione contenziosa
- Consiglio di garanzia
- Comitato per la legislazione

Regole di classificazione preliminare:
- Le categorie possibili sono SOLO queste:
  1. "Non attinenti"
  2. "Interesse industriale generale"
  3. "Interesse industria del trasporto"
  4. "Interesse trasporto marittimo"

- Pesca e diporto vanno classificati come "Non attinenti".
- La sanità NON va esclusa a priori.
- Se c'è dubbio, scegli la categoria più rilevante.
- Se un atto NON è chiaramente "Non attinenti", allora "richiede_lettura_pdf" deve essere true.
- Gli ODG in linea generale richiedono lettura del PDF, salvo caso eccezionale di chiara non attinenza.

Istruzioni di estrazione:
- Lavora solo sulle informazioni realmente presenti nella pagina e nell'elenco PDF fornito.
- Non inventare dati mancanti.
- Se un campo non è disponibile, usa stringa vuota.
- Il campo "link_pdf" deve contenere uno degli URL presenti nell'elenco PDF se l'associazione è plausibile; altrimenti stringa vuota.
- Il campo "sezione" deve riflettere la macro-sezione della pagina.
- Il campo "tipo_atto" deve essere sintetico.
- Se il nome dell'organo/commissione compare nel titolo o in altri campi testuali, usalo correttamente per identificare l'atto.
- Non restituire atti relativi agli organi esclusi anche se compaiono nella pagina o nell'elenco PDF.

Formato JSON richiesto:

[
  {{
    "ramo": "Senato",
    "data_pubblicazione": "{target_date_str}",
    "sezione": "",
    "tipo_atto": "",
    "numero": "",
    "titolo": "",
    "commissione": "",
    "seduta": "",
    "link_pdf": "",
    "categoria_preliminare": "",
    "motivazione_preliminare": "",
    "richiede_lettura_pdf": false
  }}
]

Restituisci SOLO JSON valido.
Nessun testo prima o dopo il JSON.
""".strip()


def extract_json_from_response(text: str):
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\[\s*{.*}\s*\])", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError("La risposta del modello non contiene JSON valido.")


def validate_items(items, target_date_str: str):
    allowed_categories = {
        "Non attinenti",
        "Interesse industriale generale",
        "Interesse industria del trasporto",
        "Interesse trasporto marittimo",
    }

    normalized = []

    for item in items:
        if not isinstance(item, dict):
            continue

        normalized_item = {
            "ramo": "Senato",
            "data_pubblicazione": target_date_str,
            "sezione": compact_spaces(str(item.get("sezione", ""))),
            "tipo_atto": compact_spaces(str(item.get("tipo_atto", ""))),
            "numero": compact_spaces(str(item.get("numero", ""))),
            "titolo": compact_spaces(str(item.get("titolo", ""))),
            "commissione": compact_spaces(str(item.get("commissione", ""))),
            "seduta": compact_spaces(str(item.get("seduta", ""))),
            "link_pdf": compact_spaces(str(item.get("link_pdf", ""))),
            "categoria_preliminare": compact_spaces(str(item.get("categoria_preliminare", ""))),
            "motivazione_preliminare": compact_spaces(str(item.get("motivazione_preliminare", ""))),
            "richiede_lettura_pdf": bool(item.get("richiede_lettura_pdf", False)),
        }

        if is_excluded_organ(normalized_item):
            continue

        if normalized_item["categoria_preliminare"] not in allowed_categories:
            normalized_item["categoria_preliminare"] = "Non attinenti"

        normalized.append(normalized_item)

    return normalized


def save_json(items, target_date_str: str) -> Path:
    output_path = OUTPUT_DIR / f"senato_atti_strutturati_{target_date_str}.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return output_path


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Manca la variabile d'ambiente OPENAI_API_KEY.")

    client = OpenAI()

    target_date = parse_target_date()
    target_date_str = target_date.isoformat()

    page_url = build_day_url(target_date)
    print(f"Analizzo con AI la pagina Senato del giorno {target_date_str}")

    html = fetch_html(page_url)
    page_text = extract_page_text(html)

    raw_json_path = OUTPUT_DIR / f"senato_atti_{target_date_str}.json"

    with open(raw_json_path, "r", encoding="utf-8") as f:
        raw_entries = json.load(f)

    raw_entries_json = json.dumps(raw_entries, ensure_ascii=False, indent=2)

    prompt = build_prompt(target_date_str, page_url, page_text, raw_entries_json)

    response = client.responses.create(
        model="gpt-5.4",
        input=prompt,
    )

    raw_text = response.output_text
    items = extract_json_from_response(raw_text)
    items = validate_items(items, target_date_str)

    output_path = save_json(items, target_date_str)

    print(f"Atti strutturati trovati: {len(items)}")
    print(f"File salvato in: {output_path}")


if __name__ == "__main__":
    main()