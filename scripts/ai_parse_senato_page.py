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
    "Commissione di inchiesta su emergenza sanitaria epidemiologica da SARS-CoV-2",
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

    return any(organ.lower() in searchable_text for organ in EXCLUDED_ORGANS)


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


def build_pdf_list_for_prompt(raw_entries):
    """
    Riduce l'elenco degli elementi trovati dallo scraper
    alla sola lista ordinata di PDF da fornire al modello.
    """
    pdf_list = []

    for idx, item in enumerate(raw_entries, start=1):
        link = item.get("link")
        if link:
            pdf_list.append(
                {
                    "pdf_index": idx,
                    "link_pdf": link,
                }
            )

    return json.dumps(pdf_list, ensure_ascii=False, indent=2)


def build_prompt(target_date_str: str, page_url: str, page_text: str, pdf_list_json: str) -> str:
    return f"""
Analizza la seguente pagina del Senato italiano "Ultimi atti pubblicati" relativa alla data {target_date_str}.

URL della pagina:
{page_url}

Testo della pagina:
<<<BEGIN_PAGE_TEXT>>>
{page_text}
<<<END_PAGE_TEXT>>>

ELENCO ORDINATO DEI PDF TROVATI DALLO SCRAPER:
<<<BEGIN_PDF_LIST>>>
{pdf_list_json}
<<<END_PDF_LIST>>>

Obiettivo:
1. Individuare i singoli atti/documenti pubblicati quel giorno.
2. Restituire una lista JSON di atti strutturati.
3. Non riportare nell'output gli organi esclusi.
4. NON assegnare direttamente il link PDF.
5. Per ogni atto restituisci invece il campo "pdf_index", cioè la posizione numerica (1-based) del PDF corretto nell'elenco ordinato dei PDF fornito sopra.

Regola fondamentale sui PDF:
- L'elenco PDF fornito sopra è ordinato.
- Devi usare quell'ordine.
- Non devi scegliere il PDF per similarità semantica.
- Devi associare ogni atto al suo PDF corretto tramite la posizione nell'elenco ordinato.
- Il campo "pdf_index" deve essere un intero positivo.
- Se non sei ragionevolmente sicuro della posizione, usa 0.

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
    "pdf_index": 0,
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


def validate_items(items, target_date_str: str, raw_entries: list[dict]):
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

        pdf_index_raw = item.get("pdf_index", 0)
        try:
            pdf_index = int(pdf_index_raw)
        except Exception:
            pdf_index = 0

        link_pdf = ""
        if 1 <= pdf_index <= len(raw_entries):
            link_pdf = compact_spaces(str(raw_entries[pdf_index - 1].get("link", "")))

        normalized_item = {
            "ramo": "Senato",
            "data_pubblicazione": target_date_str,
            "sezione": compact_spaces(str(item.get("sezione", ""))),
            "tipo_atto": compact_spaces(str(item.get("tipo_atto", ""))),
            "numero": compact_spaces(str(item.get("numero", ""))),
            "titolo": compact_spaces(str(item.get("titolo", ""))),
            "commissione": compact_spaces(str(item.get("commissione", ""))),
            "seduta": compact_spaces(str(item.get("seduta", ""))),
            "pdf_index": pdf_index,
            "link_pdf": link_pdf,
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

    pdf_list_json = build_pdf_list_for_prompt(raw_entries)

    prompt = build_prompt(target_date_str, page_url, page_text, pdf_list_json)

    response = client.responses.create(
        model="gpt-5.4",
        input=prompt,
    )

    raw_text = response.output_text
    items = extract_json_from_response(raw_text)
    items = validate_items(items, target_date_str, raw_entries)

    output_path = save_json(items, target_date_str)

    print(f"Atti strutturati trovati: {len(items)}")
    print(f"File salvato in: {output_path}")


if __name__ == "__main__":
    main()