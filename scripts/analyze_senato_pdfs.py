import json
import os
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import requests
from openai import OpenAI


OUTPUT_DIR = Path("data/senato")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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

RESOCONTO_KEYWORDS = [
    "porto",
    "porti",
    "portuale",
    "portualità",
    "autorità di sistema portuale",
    "marittimo",
    "marittima",
    "navigazione",
    "codice della navigazione",
    "lavoro marittimo",
    "demanio marittimo",
    "economia del mare",
    "autostrade del mare",
    "sea modal shift",
    "shipping",
    "logistica",
    "trasporto merci",
    "trasporti",
    "fuelEU".lower(),
    "ets",
]


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


def is_excluded_organ(item) -> bool:
    text = " ".join(
        [
            str(item.get("commissione", "")),
            str(item.get("titolo", "")),
            str(item.get("tipo_atto", "")),
            str(item.get("sezione", "")),
        ]
    ).lower()

    return any(org.lower() in text for org in EXCLUDED_ORGANS)


def is_odg(item) -> bool:
    text = " ".join(
        [
            str(item.get("tipo_atto", "")),
            str(item.get("titolo", "")),
            str(item.get("sezione", "")),
        ]
    ).lower()
    return "o.d.g" in text or "odg" in text or "ordine del giorno" in text


def is_resoconto(item) -> bool:
    text = " ".join(
        [
            str(item.get("tipo_atto", "")),
            str(item.get("titolo", "")),
            str(item.get("sezione", "")),
        ]
    ).lower()
    return "resoconto" in text


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


def extract_seduta_date(pdf_text: str) -> str:
    pattern = re.compile(
        r"\b(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)\s+\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4}\b",
        flags=re.IGNORECASE,
    )
    match = pattern.search(pdf_text[:15000])
    return compact_spaces(match.group(0)) if match else ""


def extract_emendamenti_snippets(pdf_text: str) -> list[str]:
    snippets = []
    patterns = [
        r"termine\s+per\s+la\s+presentazione\s+degli\s+emendamenti",
        r"presentazione\s+degli\s+emendamenti",
        r"termine\s+degli\s+emendamenti",
    ]

    text = pdf_text
    for pat in patterns:
        for match in re.finditer(pat, text, flags=re.IGNORECASE):
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 220)
            snippet = compact_spaces(text[start:end])
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            if len(snippets) >= 5:
                return snippets

    return snippets


def extract_audizioni_snippets(pdf_text: str) -> list[str]:
    snippets = []
    patterns = [
        r"audizione\s+di",
        r"audizione\s+del",
        r"audizione\s+della",
        r"audizioni",
        r"audizione\s+informale",
    ]

    text = pdf_text
    for pat in patterns:
        for match in re.finditer(pat, text, flags=re.IGNORECASE):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 260)
            snippet = compact_spaces(text[start:end])
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            if len(snippets) >= 5:
                return snippets

    return snippets


def scan_resoconto_keywords(pdf_text: str) -> list[str]:
    lowered = pdf_text.lower()
    found = []
    for kw in RESOCONTO_KEYWORDS:
        if kw in lowered and kw not in found:
            found.append(kw)
    return found


def build_pdf_prompt(item, pdf_text):
    return f"""
Analizza il seguente documento parlamentare del Senato.

Tipo atto: {item["tipo_atto"]}
Titolo: {item["titolo"]}
Commissione: {item["commissione"]}

Testo estratto dal PDF:
<<<BEGIN_TEXT>>>
{pdf_text}
<<<END_TEXT>>>

CRITERIO DI ANALISI (IMPORTANTE):

Molti documenti del Senato, in particolare ODG Assemblea e ODG Commissioni, sono documenti compositi con molti punti diversi.

NON devi classificare il documento in base al tema prevalente.

Devi verificare se anche UNA SOLA PARTE del documento contiene riferimenti a:
- trasporto marittimo
- navigazione
- porti
- autorità di sistema portuale
- codice della navigazione
- lavoro marittimo
- demanio marittimo
- economia del mare

Se anche una sola parte del documento contiene questi riferimenti, la classificazione deve essere:
Interesse trasporto marittimo

Se il documento contiene riferimenti a:
- industria
- politica industriale
- imprese
- energia
- lavoro
- occupazione
- relazioni industriali
- contrattazione collettiva
- salario minimo
- retribuzioni
- CCNL
- politiche per le imprese
- transizione industriale
- crisi industriali
- sostegno alle imprese

ma NON contiene riferimenti specifici al trasporto marittimo, allora la classificazione deve essere:
Interesse industriale generale

DDL e atti che riguardano prevalentemente:
- minori
- famiglia
- scuola
- cultura
- sanità
- giustizia
- temi sociali non economici

devono restare "Non attinenti", salvo che nel testo non emergano in modo chiaro profili di industria, imprese, lavoro, energia o trasporti.

Solo se nel documento NON compare nessun riferimento a:
- marittimo
- trasporti
- industria
- lavoro
- imprese

allora la classificazione può essere:
Non attinenti

Per ODG e altri documenti compositi:
- cerca i singoli punti
- cita nella motivazione il punto o il contenuto che giustifica la classificazione

Categorie possibili (solo queste):
- Non attinenti
- Interesse industriale generale
- Interesse industria del trasporto
- Interesse trasporto marittimo

Restituisci SOLO JSON valido nel seguente formato:

{{
  "categoria_finale": "...",
  "motivazione_finale": "...",
  "estratto_rilevante": "...",
  "termine_emendamenti": [],
  "audizioni": []
}}
""".strip()


def extract_json_from_response(text: str):
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\{{.*\}})", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError("La risposta del modello non contiene JSON valido.")


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

        categoria = item.get("categoria_preliminare", "Non attinenti")
        link = item.get("link_pdf", "")

        item["data_seduta"] = ""
        item["termine_emendamenti"] = []
        item["audizioni"] = []
        item["resoconto_keywords_found"] = []
        item["resoconto_alert"] = False

        if not link:
            item["categoria_finale"] = categoria
            item["motivazione_finale"] = item.get("motivazione_preliminare", "")
            item["estratto_rilevante"] = ""
            results.append(item)
            continue

        print("Analizzo PDF:", link)

        try:
            pdf_bytes = download_pdf(link)
            pdf_text = extract_pdf_text(pdf_bytes)

            if is_odg(item):
                item["data_seduta"] = extract_seduta_date(pdf_text)
                item["termine_emendamenti"] = extract_emendamenti_snippets(pdf_text)
                item["audizioni"] = extract_audizioni_snippets(pdf_text)

                prompt = build_pdf_prompt(item, pdf_text)
                response = client.responses.create(
                    model="gpt-5.4",
                    input=prompt,
                )
                parsed = extract_json_from_response(response.output_text)

                item["categoria_finale"] = parsed.get("categoria_finale", categoria)
                item["motivazione_finale"] = parsed.get(
                    "motivazione_finale", item.get("motivazione_preliminare", "")
                )
                item["estratto_rilevante"] = parsed.get("estratto_rilevante", "")

                ai_em = parsed.get("termine_emendamenti", [])
                if isinstance(ai_em, list):
                    for x in ai_em:
                        x = compact_spaces(str(x))
                        if x and x not in item["termine_emendamenti"]:
                            item["termine_emendamenti"].append(x)

                ai_aud = parsed.get("audizioni", [])
                if isinstance(ai_aud, list):
                    for x in ai_aud:
                        x = compact_spaces(str(x))
                        if x and x not in item["audizioni"]:
                            item["audizioni"].append(x)

                results.append(item)
                continue

            if is_resoconto(item):
                found = scan_resoconto_keywords(pdf_text)
                item["resoconto_keywords_found"] = found
                item["resoconto_alert"] = bool(found)
                item["categoria_finale"] = categoria
                item["motivazione_finale"] = item.get("motivazione_preliminare", "")
                item["estratto_rilevante"] = ""
                results.append(item)
                continue

            if categoria == "Non attinenti":
                item["categoria_finale"] = categoria
                item["motivazione_finale"] = item.get("motivazione_preliminare", "")
                item["estratto_rilevante"] = ""
                results.append(item)
                continue

            MAX_CHARS = 20000
            if len(pdf_text) > MAX_CHARS:
                pdf_text = pdf_text[:MAX_CHARS]

            prompt = build_pdf_prompt(item, pdf_text)
            response = client.responses.create(
                model="gpt-5.4",
                input=prompt,
            )
            parsed = extract_json_from_response(response.output_text)

            item["categoria_finale"] = parsed.get("categoria_finale", categoria)
            item["motivazione_finale"] = parsed.get(
                "motivazione_finale", item.get("motivazione_preliminare", "")
            )
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