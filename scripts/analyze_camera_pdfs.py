import json
import os
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import requests
from openai import OpenAI


OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RULES_PATH = Path("config/senato_monitor_rules.json")


def load_rules():
    with RULES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


RULES = load_rules()
RESOCONTO_KEYWORDS = [x.lower() for x in RULES["resoconto_keywords"]]
NORMATIVE_PATTERNS = RULES["normative_patterns"]
CONFITARMA_KB = RULES.get("confitarma_kb", {})


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


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

def is_real_camera_pdf_url(url: str) -> bool:
    url = (url or "").strip().lower()

    if not url:
        return False

    if url.endswith(".pdf"):
        return True

    if "documenti.camera.it" in url and "tipodoc=pdf" in url:
        return True

    return False

def download_pdf(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def extract_pdf_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts = []
    for page in doc:
        parts.append(page.get_text())
    return "\n".join(parts)


def extract_seduta_date(pdf_text: str) -> str:
    pattern = re.compile(
        r"\b(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)\s+\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4}\b",
        flags=re.IGNORECASE,
    )
    match = pattern.search(pdf_text[:20000])
    return compact_spaces(match.group(0)) if match else ""


def extract_emendamenti_snippets(pdf_text: str) -> list[str]:
    snippets = []
    patterns = [
        r"termine\s+per\s+la\s+presentazione\s+degli\s+emendamenti",
        r"presentazione\s+degli\s+emendamenti",
        r"termine\s+degli\s+emendamenti",
    ]

    for pat in patterns:
        for match in re.finditer(pat, pdf_text, flags=re.IGNORECASE):
            start = max(0, match.start() - 120)
            end = min(len(pdf_text), match.end() + 220)
            snippet = compact_spaces(pdf_text[start:end])
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
        r"audizione\s+dei",
        r"audizione\s+delle",
        r"audizioni",
    ]

    for pat in patterns:
        for match in re.finditer(pat, pdf_text, flags=re.IGNORECASE):
            start = match.start()
            end = min(len(pdf_text), match.end() + 300)
            snippet = compact_spaces(pdf_text[start:end])
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


def extract_normative_hits(pdf_text: str) -> list[str]:
    lowered = pdf_text.lower()
    found = []

    for entry in NORMATIVE_PATTERNS:
        for pat in entry["patterns"]:
            if re.search(pat, lowered, flags=re.IGNORECASE):
                if entry["label"] not in found:
                    found.append(entry["label"])
                break

    return found


def extract_confitarma_kb_hits(pdf_text: str) -> dict:
    lowered = pdf_text.lower()

    result = {
        "keyword_categories": [],
        "keyphrases": [],
        "norm_refs_italia": [],
        "norm_refs_ue_internazionale": [],
        "programs_tools": [],
        "entities": [],
    }

    for category, values in CONFITARMA_KB.get("keywords", {}).items():
        for value in values:
            if value.lower() in lowered:
                result["keyword_categories"].append(category)
                break

    for value in CONFITARMA_KB.get("keyphrases", []):
        if value.lower() in lowered:
            result["keyphrases"].append(value)

    for value in CONFITARMA_KB.get("norm_refs", {}).get("italia", []):
        if value.lower() in lowered:
            result["norm_refs_italia"].append(value)

    for value in CONFITARMA_KB.get("norm_refs", {}).get("ue_internazionale", []):
        if value.lower() in lowered:
            result["norm_refs_ue_internazionale"].append(value)

    for value in CONFITARMA_KB.get("programs_tools", []):
        if value.lower() in lowered:
            result["programs_tools"].append(value)

    for value in CONFITARMA_KB.get("entities", []):
        if value.lower() in lowered:
            result["entities"].append(value)

    for key in result:
        seen = set()
        deduped = []
        for x in result[key]:
            if x not in seen:
                seen.add(x)
                deduped.append(x)
        result[key] = deduped

    return result


def merge_normative_hits(item: dict) -> list[str]:
    merged = []

    for x in item.get("normative_hits", []) or []:
        if x not in merged:
            merged.append(x)

    kb_hits = item.get("confitarma_kb_hits", {}) or {}
    for x in kb_hits.get("norm_refs_italia", []):
        if x not in merged:
            merged.append(x)
    for x in kb_hits.get("norm_refs_ue_internazionale", []):
        if x not in merged:
            merged.append(x)

    return merged


def build_pdf_prompt(item, pdf_text):
    return f"""
Analizza il seguente documento parlamentare della Camera dei deputati.

Tipo atto: {item["tipo_atto"]}
Titolo: {item["titolo"]}
Commissione: {item["commissione"]}

Testo estratto dal PDF:
<<<BEGIN_TEXT>>>
{pdf_text}
<<<END_TEXT>>>

Regole di classificazione:

1. I documenti compositi NON vanno classificati in base al tema prevalente.
2. Devi cercare i singoli punti.
3. Se anche UNA SOLA PARTE contiene riferimenti espliciti e specifici a:
- trasporto marittimo
- navigazione
- porti
- autorità di sistema portuale
- codice della navigazione
- lavoro marittimo
- demanio marittimo
- economia del mare
- autostrade del mare
- sea modal shift

allora la classificazione deve essere:
Interesse trasporto marittimo

4. Non basta una parola generica o ambigua da sola.
Esempi di parole che DA SOLE non bastano:
- concessioni
- infrastrutture
- ambiente
- energia
- trasporti
- mare

5. Se il documento contiene riferimenti a:
- imprese
- politica industriale
- energia
- lavoro
- occupazione
- relazioni industriali
- contrattazione collettiva
- salario minimo
- retribuzioni
- CCNL
- crisi industriali
- sostegno alle imprese
- previdenza di categorie economiche
- logistica
- spedizionieri
- corrieri
- filiera del trasporto

ma NON contiene riferimenti specifici al trasporto marittimo, allora la classificazione può essere:
Interesse industriale generale
oppure
Interesse industria del trasporto
se il focus è chiaramente su trasporto, logistica, spedizionieri, corrieri o filiera trasporto.

6. DDL e atti che riguardano prevalentemente:
- minori
- famiglia
- scuola
- cultura
- sanità
- giustizia
- temi sociali non economici

devono restare "Non attinenti", salvo che il testo contenga in modo chiaro e centrale profili di imprese, energia, lavoro, industria o trasporti.

7. Non classificare come "Interesse industriale generale" un atto solo perché coinvolge genericamente fornitori, piattaforme, sanzioni o soggetti economici.

Categorie possibili (solo queste):
- Non attinenti
- Interesse industriale generale
- Interesse industria del trasporto
- Interesse trasporto marittimo

Restituisci SOLO JSON valido nel formato:

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

    match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError("La risposta del modello non contiene JSON valido.")


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY mancante")

    client = OpenAI()
    target_date = parse_target_date()

    input_file = OUTPUT_DIR / f"camera_atti_strutturati_{target_date}.json"

    with open(input_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        output_file = OUTPUT_DIR / f"camera_atti_analizzati_{target_date}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        print("Nessun atto da analizzare.")
        print("File creato:", output_file)
        return

    results = []

    for item in items:
        categoria = item.get("categoria_preliminare", "Non attinenti")
        link = item.get("link_pdf", "")

        item["data_seduta"] = ""
        item["termine_emendamenti"] = []
        item["audizioni"] = []
        item["resoconto_keywords_found"] = []
        item["resoconto_alert"] = False
        item["normative_hits"] = []
        item["confitarma_kb_hits"] = {
            "keyword_categories": [],
            "keyphrases": [],
            "norm_refs_italia": [],
            "norm_refs_ue_internazionale": [],
            "programs_tools": [],
            "entities": [],
        }

        if not link or not is_real_camera_pdf_url(link):
            item["categoria_finale"] = categoria
            if not link:
                item["motivazione_finale"] = item.get("motivazione_preliminare", "")
            else:
                item["motivazione_finale"] = (
                    item.get("motivazione_preliminare", "")
                    + " Link non riconosciuto come PDF diretto Camera: analisi PDF saltata."
                ).strip()
            item["estratto_rilevante"] = ""
            results.append(item)
            continue

        # SKIP come Senato: non analizzare PDF inutili
        if categoria == "Non attinenti" and not is_odg(item) and not is_resoconto(item):
            item["categoria_finale"] = categoria
            item["motivazione_finale"] = (
                item.get("motivazione_preliminare", "")
                + " PDF non analizzato: documento non rilevante (logica Senato)."
            ).strip()
            item["estratto_rilevante"] = ""
            results.append(item)
            continue
        print("Analizzo PDF:", link)
        
        try:
            pdf_bytes = download_pdf(link)
            pdf_text = extract_pdf_text(pdf_bytes)

            item["normative_hits"] = extract_normative_hits(pdf_text)
            item["confitarma_kb_hits"] = extract_confitarma_kb_hits(pdf_text)
            item["normative_hits"] = merge_normative_hits(item)

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

                results.append(item)
                continue

            if is_resoconto(item):
                found = scan_resoconto_keywords(pdf_text)
                item["resoconto_keywords_found"] = found
                item["resoconto_alert"] = bool(found)
                item["categoria_finale"] = "Non attinenti"
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

    output_file = OUTPUT_DIR / f"camera_atti_analizzati_{target_date}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("File creato:", output_file)


if __name__ == "__main__":
    main()