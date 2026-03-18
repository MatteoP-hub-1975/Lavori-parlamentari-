import json
import os
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup
from openai import OpenAI


OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RULES_PATH = Path("config/senato_monitor_rules.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/pdf,application/octet-stream,text/html,*/*",
}


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


def normalize_camera_pdf_candidate(url: str) -> str:
    url = (url or "").strip()

    if not url:
        return ""

    lowered = url.lower()

    if "documenti.camera.it" not in lowered:
        return url

    url = re.sub(r"tipoDoc=documento", "tipoDoc=pdf", url, flags=re.IGNORECASE)
    url = re.sub(r"doc=intero\b", "doc=INTERO", url, flags=re.IGNORECASE)

    return url


def is_real_camera_pdf_url(url: str) -> bool:
    url = normalize_camera_pdf_candidate(url).lower()

    if not url:
        return False

    if "votazioni" in url:
        return False

    if url.endswith(".pdf"):
        return True

    if "documenti.camera.it" in url and "getdocumento.ashx" in url:
        return True

    if "documenti.camera.it" in url and "tipodoc=pdf" in url:
        return True

    return False


def download_pdf(url: str) -> bytes:
    url = normalize_camera_pdf_candidate(url)

    if not url:
        raise ValueError("URL vuoto")

    if "votazioni" in url.lower():
        raise ValueError("Link non PDF (pagina votazioni)")

    print("Download URL finale:", url)

    response = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)

    if response.status_code != 200:
        raise ValueError(f"Errore HTTP {response.status_code}")

    content_type = response.headers.get("Content-Type", "").lower()

    if "application/pdf" in content_type:
        return response.content

    if url.lower().endswith(".pdf"):
        return response.content

    if "text/html" in content_type or "<html" in response.text[:500].lower():
        soup = BeautifulSoup(response.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            href_lower = href.lower()

            if ".pdf" in href_lower or "tipodoc=pdf" in href_lower:
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = "https://documenti.camera.it" + href
                elif not href.startswith("http"):
                    href = "https://documenti.camera.it/" + href.lstrip("/")

                href = normalize_camera_pdf_candidate(href)
                print("Trovato PDF dentro pagina:", href)

                r2 = requests.get(href, headers=HEADERS, timeout=60, allow_redirects=True)
                if r2.status_code == 200:
                    return r2.content

        raise ValueError("HTML senza PDF interno")

    return response.content


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


def first_excerpt_from_terms(text: str, terms: list[str], radius: int = 220) -> str:
    lowered = text.lower()
    for term in terms:
        term_l = term.lower()
        idx = lowered.find(term_l)
        if idx != -1:
            start = max(0, idx - radius)
            end = min(len(text), idx + len(term) + radius)
            return compact_spaces(text[start:end])
    return ""


def analyze_with_kb(item: dict, pdf_text: str) -> dict:
    titolo = compact_spaces(item.get("titolo", ""))
    combined = f"{titolo}\n{pdf_text[:50000]}"
    combined_lower = combined.lower()

    normative_hits = extract_normative_hits(combined)
    kb_hits = extract_confitarma_kb_hits(combined)

    all_terms_for_excerpt = []
    all_terms_for_excerpt.extend(normative_hits)
    all_terms_for_excerpt.extend(kb_hits.get("keyphrases", []))
    all_terms_for_excerpt.extend(kb_hits.get("norm_refs_italia", []))
    all_terms_for_excerpt.extend(kb_hits.get("norm_refs_ue_internazionale", []))
    all_terms_for_excerpt.extend(kb_hits.get("entities", []))

    keyword_categories = set(kb_hits.get("keyword_categories", []))

    maritime_categories = {
        "porti_adsp_infrastrutture_servizi_tecnico_nautici",
        "trasporto_marittimo_short_sea_logistica_incentivi",
        "ordinamento_marittimo_registri_bandiera",
        "lavoro_marittimo_relazioni_industriali_welfare",
        "sanita_marittima_sanita_di_bordo",
        "transizione_ecologica_combustibili_ets_fueleu_tecnica_navale",
        "sicurezza_marittima_cyber_security",
        "relazioni_internazionali_rotte_sanzioni_compliance",
        "finanza_fiscalita_aiuti_tassonomia",
        "education_capitale_umano",
    }

    maritime_title_terms = [
        "trasporto marittimo",
        "marittim",
        "navigaz",
        "porto",
        "portual",
        "adsp",
        "autorità di sistema portuale",
        "demanio marittimo",
        "codice della navigazione",
        "economia del mare",
        "autostrade del mare",
        "sea modal shift",
        "gente di mare",
        "lavoro marittimo",
        "fueleu maritime",
        "ets marittimo",
        "cold ironing",
        "shore power",
    ]

    transport_title_terms = [
        "trasporto",
        "trasporti",
        "logistica",
        "spedizion",
        "corrier",
        "mobilità",
        "rete transeuropea",
        "ten-t",
        "infrastrutture",
        "autostrad",
        "gallerie stradali",
    ]

    industrial_general_terms = [
        "imprese",
        "impresa",
        "industria",
        "industriale",
        "energia",
        "lavoro",
        "occupazione",
        "internazionalizzazione",
        "sistema produttivo",
        "pnrr",
        "made in italy",
        "aiuti di stato",
        "fondo",
        "previdenza",
        "cassa depositi e prestiti",
    ]

    maritime_hit = bool(keyword_categories & maritime_categories) or any(
        term in combined_lower for term in maritime_title_terms
    )

    transport_hit = any(term in combined_lower for term in transport_title_terms)
    industrial_hit = any(term in combined_lower for term in industrial_general_terms)

    excerpt = first_excerpt_from_terms(
        combined,
        all_terms_for_excerpt
        + maritime_title_terms
        + transport_title_terms
        + industrial_general_terms,
    )

    if maritime_hit:
        reasons = []
        if keyword_categories & maritime_categories:
            reasons.append(
                "categorie KB rilevate: " + ", ".join(sorted(keyword_categories & maritime_categories))
            )
        if normative_hits:
            reasons.append("normative rilevate: " + ", ".join(normative_hits[:5]))

        motivazione = (
            "Il documento contiene riferimenti coerenti con il perimetro marittimo individuato dal KB Confitarma"
        )
        if reasons:
            motivazione += " (" + "; ".join(reasons) + ")."
        else:
            motivazione += "."

        return {
            "categoria_finale": "Interesse trasporto marittimo",
            "motivazione_finale": motivazione,
            "estratto_rilevante": excerpt,
            "normative_hits": normative_hits,
            "confitarma_kb_hits": kb_hits,
        }

    if transport_hit:
        motivazione = (
            "Il documento contiene riferimenti al comparto trasporti/logistica, "
            "ma non emergono elementi specifici sufficienti per il perimetro marittimo."
        )
        return {
            "categoria_finale": "Interesse industria del trasporto",
            "motivazione_finale": motivazione,
            "estratto_rilevante": excerpt,
            "normative_hits": normative_hits,
            "confitarma_kb_hits": kb_hits,
        }

    if industrial_hit:
        motivazione = (
            "Il documento presenta profili di impresa, industria, energia, lavoro o sistema produttivo, "
            "senza specifica connotazione marittima o di trasporto."
        )
        return {
            "categoria_finale": "Interesse industriale generale",
            "motivazione_finale": motivazione,
            "estratto_rilevante": excerpt,
            "normative_hits": normative_hits,
            "confitarma_kb_hits": kb_hits,
        }

    return {
        "categoria_finale": "Non attinenti",
        "motivazione_finale": (
            "Dalla lettura del PDF e dalla verifica con KB/normative non emergono riferimenti sufficienti "
            "al perimetro marittimo, del trasporto o industriale rilevante per il monitor."
        ),
        "estratto_rilevante": excerpt,
        "normative_hits": normative_hits,
        "confitarma_kb_hits": kb_hits,
    }


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
    client = OpenAI() if os.environ.get("OPENAI_API_KEY") else None
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
        categoria_preliminare = item.get("categoria_preliminare", "Non attinenti")
        link = normalize_camera_pdf_candidate(item.get("link_pdf", ""))
        item["link_pdf"] = link

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
        item["estratto_rilevante"] = ""

        if not link or not is_real_camera_pdf_url(link):
            item["categoria_finale"] = categoria_preliminare
            if not link:
                item["motivazione_finale"] = item.get("motivazione_preliminare", "")
            else:
                item["motivazione_finale"] = (
                    item.get("motivazione_preliminare", "")
                    + " Link non riconosciuto come PDF diretto Camera: analisi PDF saltata."
                ).strip()
            results.append(item)
            continue

        print("Analizzo PDF:", link)

        try:
            pdf_bytes = download_pdf(link)
            pdf_text = extract_pdf_text(pdf_bytes)

            if not compact_spaces(pdf_text):
                item["categoria_finale"] = "Non attinenti"
                item["motivazione_finale"] = (
                    item.get("motivazione_preliminare", "")
                    + " PDF vuoto o non leggibile."
                ).strip()
                results.append(item)
                continue

            if is_resoconto(item):
                found = scan_resoconto_keywords(pdf_text)
                item["resoconto_keywords_found"] = found
                item["resoconto_alert"] = bool(found)
                item["normative_hits"] = extract_normative_hits(pdf_text)
                item["confitarma_kb_hits"] = extract_confitarma_kb_hits(pdf_text)
                item["normative_hits"] = merge_normative_hits(item)
                item["categoria_finale"] = "Non attinenti"
                item["motivazione_finale"] = item.get("motivazione_preliminare", "")
                results.append(item)
                continue

            kb_analysis = analyze_with_kb(item, pdf_text)
            item["normative_hits"] = kb_analysis.get("normative_hits", [])
            item["confitarma_kb_hits"] = kb_analysis.get("confitarma_kb_hits", {})
            item["normative_hits"] = merge_normative_hits(item)

            item["categoria_finale"] = kb_analysis.get("categoria_finale", categoria_preliminare)
            item["motivazione_finale"] = kb_analysis.get(
                "motivazione_finale",
                item.get("motivazione_preliminare", ""),
            )
            item["estratto_rilevante"] = kb_analysis.get("estratto_rilevante", "")

            if is_odg(item):
                item["data_seduta"] = extract_seduta_date(pdf_text)
                item["termine_emendamenti"] = extract_emendamenti_snippets(pdf_text)
                item["audizioni"] = extract_audizioni_snippets(pdf_text)

                if client is not None:
                    prompt = build_pdf_prompt(item, pdf_text[:20000])
                    response = client.responses.create(
                        model="gpt-5.4",
                        input=prompt,
                    )
                    parsed = extract_json_from_response(response.output_text)

                    item["categoria_finale"] = parsed.get(
                        "categoria_finale",
                        item["categoria_finale"],
                    )
                    item["motivazione_finale"] = parsed.get(
                        "motivazione_finale",
                        item["motivazione_finale"],
                    )
                    item["estratto_rilevante"] = parsed.get(
                        "estratto_rilevante",
                        item["estratto_rilevante"],
                    )

        except Exception as e:
            item["categoria_finale"] = categoria_preliminare
            item["motivazione_finale"] = f"Errore analisi PDF: {e}"
            item["estratto_rilevante"] = ""

        results.append(item)

    output_file = OUTPUT_DIR / f"camera_atti_analizzati_{target_date}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("File creato:", output_file)


if __name__ == "__main__":
    main()