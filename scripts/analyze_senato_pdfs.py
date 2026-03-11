import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
import fitz  # PyMuPDF
from openai import OpenAI

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
    text = " ".join(
        [
            str(item.get("commissione", "")),
            str(item.get("titolo", "")),
            str(item.get("tipo_atto", "")),
        ]
    ).lower()

    return any(org.lower() in text for org in EXCLUDED_ORGANS)
    
OUTPUT_DIR = Path("data/senato")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)



def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


def download_pdf(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def extract_pdf_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = []
    for page in doc:
        text.append(page.get_text())
    return "\n".join(text)


def build_prompt(item, pdf_text):
    return f"""
Analizza il seguente documento parlamentare del Senato.

Tipo atto: {item["tipo_atto"]}
Titolo: {item["titolo"]}
Commissione: {item["commissione"]}

Testo estratto dal PDF:
<<<BEGIN_TEXT>>>
{pdf_text}
<<<END_TEXT>>>

Classifica definitivamente il documento in una delle categorie:
Nei documenti eterogenei o composti da più punti, ordini del giorno, pareri, provvedimenti o materie diverse, non devi basarti solo sul tema prevalente o sull’oggetto complessivo del documento. Se anche una sola parte del testo contiene contenuti specificamente riconducibili al trasporto marittimo, alla navigazione, al lavoro marittimo, ai porti, all’ordinamento marittimo o ad altre materie del perimetro marittimo rilevante, il documento non può essere classificato come "Non attinenti" e deve essere classificato almeno come "Interesse trasporto marittimo".
Se il documento contiene riferimenti a temi di lavoro o relazioni industriali generali come salario minimo, retribuzione, contrattazione collettiva, CCNL, ferie, distacchi sindacali, rappresentanza sindacale, condizioni di lavoro o altri istituti generali del diritto del lavoro, e tali riferimenti non riguardano specificamente il trasporto marittimo o il lavoro marittimo, il documento deve essere classificato come "Interesse industriale generale".
La presenza di uno solo di questi temi è sufficiente per escludere la classificazione "Non attinenti".
- Non attinenti
- Interesse industriale generale
- Interesse industria del trasporto
- Interesse trasporto marittimo

Restituisci JSON:

{{
 "categoria_finale": "...",
 "motivazione_finale": "...",
 "estratto_rilevante": "..."
}}
"""


def main():

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY mancante")

    client = OpenAI()

    target_date = parse_target_date()

    input_file = OUTPUT_DIR / f"senato_atti_strutturati_{target_date}.json"

    with open(input_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    results = []

    for item in items:

        if is_excluded_organ(item):
            continue
        categoria = item.get("categoria_preliminare")

        if categoria == "Non attinenti":
            results.append(item)
            continue

        link = item.get("link_pdf")

        if not link:
            results.append(item)
            continue

        print("Analizzo PDF:", link)

        try:

            pdf_bytes = download_pdf(link)

            pdf_text = extract_pdf_text(pdf_bytes)
            tipo_atto = str(item.get("tipo_atto", "")).lower()

            if "o.d.g" not in tipo_atto and "ordine del giorno" not in tipo_atto:
                MAX_CHARS = 20000
                if len(pdf_text) > MAX_CHARS:
                    pdf_text = pdf_text[:MAX_CHARS]
            print("LUNGHEZZA PDF TEXT:", len(pdf_text))
            print("TIPO ATTO:", item.get("tipo_atto"), "| TITOLO:", item.get("titolo"))

            debug_path = OUTPUT_DIR / f"debug_pdf_text_{target_date}.txt"
            debug_path.write_text(pdf_text, encoding="utf-8")


            prompt = build_prompt(item, pdf_text)

            response = client.responses.create(
                model="gpt-5.4",
                input=prompt,
            )

            output = response.output_text

            try:
                parsed = json.loads(output)
            except:
                parsed = {
                    "categoria_finale": categoria,
                    "motivazione_finale": "Errore parsing risposta AI",
                    "estratto_rilevante": ""
                }

            item["categoria_finale"] = parsed.get("categoria_finale", categoria)
            item["motivazione_finale"] = parsed.get("motivazione_finale", "")
            item["estratto_rilevante"] = parsed.get("estratto_rilevante", "")

        except Exception as e:

            item["categoria_finale"] = categoria
            item["motivazione_finale"] = f"Errore analisi PDF: {e}"
            item["estratto_rilevante"] = ""

        results.append(item)

    output_file = OUTPUT_DIR / f"senato_atti_analizzati_{target_date}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("File creato:", output_file)


if __name__ == "__main__":
    main()
