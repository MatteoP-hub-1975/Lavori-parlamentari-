import json
import os
import re
import smtplib
from copy import deepcopy
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

import requests
from pdfminer.high_level import extract_text
from openai import OpenAI


# =========================================================
# CONFIG
# =========================================================
RULES_FILE = os.path.join(os.getcwd(), "config", "senato_monitor_rules.json")
PDF_LOCAL_PATH = os.path.join(os.getcwd(), "camera.pdf")
STATE_DIR = os.path.join(os.getcwd(), "data", "camera_ai")
STATE_FILE = os.path.join(STATE_DIR, "camera_ai_last.json")

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"

EMAIL_USER_ENV = "EMAIL_USER"
EMAIL_PASS_ENV = "EMAIL_PASS"
EMAIL_TO_ENV = "EMAIL_TO"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

MAX_LOOKBACK_DAYS = 10

CATEGORY_MARITTIMO = "INTERESSE TRASPORTO MARITTIMO"
CATEGORY_TRASPORTO = "INTERESSE INDUSTRIA DEL TRASPORTO"
CATEGORY_INDUSTRIA = "INTERESSE INDUSTRIALE GENERALE"

ALLOWED_CATEGORIES = {
    CATEGORY_MARITTIMO,
    CATEGORY_TRASPORTO,
    CATEGORY_INDUSTRIA,
}

OPENAI_MODEL = "gpt-5.4"

SYSTEM_PROMPT = """
Sei un assistente esperto di analisi parlamentare italiana.

Devi analizzare un bollettino ufficiale della Camera dei Deputati.

OBIETTIVO:
Individuare gli atti parlamentari rilevanti per:
- INTERESSE TRASPORTO MARITTIMO
- INTERESSE INDUSTRIA DEL TRASPORTO
- INTERESSE INDUSTRIALE GENERALE

Usa il knowledge base fornito solo come supporto valutativo, senza filtrare in modo eccessivo.

REGOLE FONDAMENTALI:
1. Non inventare informazioni.
2. Non dedurre contenuti non presenti nel testo.
3. Non duplicare atti uguali.
4. Se un dato non è presente, restituisci stringa vuota.
5. Non includere riunioni prive di atti concreti.
6. Usa il knowledge base solo per valutare la rilevanza, non per aggiungere contenuti.
7. Restituisci nomi di organo puliti, sintetici e coerenti.
8. Se lo stesso atto compare più volte, restituiscilo una sola volta.
9. Restituisci esclusivamente JSON valido (nessun testo extra).

CRITERI DI CLASSIFICAZIONE:

- INTERESSE TRASPORTO MARITTIMO:
  solo se il contenuto è chiaramente marittimo, portuale, navale o riguarda trasporto via mare.

- INTERESSE INDUSTRIA DEL TRASPORTO:
  include trasporti, logistica, infrastrutture, mobilità (anche non marittimi).

- INTERESSE INDUSTRIALE GENERALE:
  include economia, lavoro, industria, energia, PNRR, competitività, innovazione.

REGOLE IMPORTANTI:
10. “salario minimo”, lavoro e occupazione sono SEMPRE rilevanti almeno come INDUSTRIALE GENERALE.
11. Termini come “MIT”, “innovazione”, “digitalizzazione”, “salute e sicurezza” NON bastano da soli per il marittimo.
12. Se un atto è importante ma non marittimo, includilo comunque nelle altre categorie.
13. In caso di dubbio, includi se esiste una motivazione concreta.

OUTPUT:
Per ogni atto restituisci:
- data_riunione
- organo
- categoria
- atto_numero
- motivazione (breve e concreta)
- parole_chiave (solo termini presenti nel testo)
- scadenza_emendamenti
"""
USER_PROMPT_TEMPLATE = """
DATA OGGI: {today}

KNOWLEDGE BASE CONFITARMA:
{rules_json}

TESTO BOLLETTINO:
{text}

ISTRUZIONI OPERATIVE:

1. Analizza il bollettino.
2. Estrai gli atti rilevanti.
3. Considera SOLO atti con data uguale o successiva a DATA OGGI.
4. Non duplicare atti identici.
5. NON limitarti al solo ambito marittimo.
6. NON escludere automaticamente temi economici o del lavoro.
7. Classifica ogni atto in UNA SOLA categoria tra:
   - INTERESSE TRASPORTO MARITTIMO
   - INTERESSE INDUSTRIA DEL TRASPORTO
   - INTERESSE INDUSTRIALE GENERALE
8. Escludi solo atti chiaramente non rilevanti.

Formato output JSON (obbligatorio):

{{
  "atti_rilevanti": [
    {{
      "data_riunione": "",
      "organo": "",
      "categoria": "",
      "atto_numero": "",
      "motivazione": "",
      "parole_chiave": [],
      "scadenza_emendamenti": ""
    }}
  ]
}}
"""
# =========================================================
# UTILS GENERALI
# =========================================================
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = text.replace("’", "'")
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_compare(text: str) -> str:
    return normalize_text(text).lower()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(path: str, data: Dict[str, Any]) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_date_it(date_str: str) -> Optional[datetime.date]:
    if not date_str:
        return None

    s = normalize_text(date_str)
    s = re.sub(r"\(\*\)", "", s).strip()

    mesi = {
        "gennaio": 1,
        "febbraio": 2,
        "marzo": 3,
        "aprile": 4,
        "maggio": 5,
        "giugno": 6,
        "luglio": 7,
        "agosto": 8,
        "settembre": 9,
        "ottobre": 10,
        "novembre": 11,
        "dicembre": 12,
    }

    m = re.search(
        r"(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)?\s*(\d{1,2})\s+([a-zà]+)\s+(\d{4})",
        s,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    day = int(m.group(2))
    month_name = m.group(3).lower()
    year = int(m.group(4))
    month = mesi.get(month_name)
    if not month:
        return None

    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


# =========================================================
# TROVA PDF CAMERA
# =========================================================
def candidate_camera_urls(date_obj: datetime) -> List[str]:
    dd = date_obj.day
    mm = date_obj.month
    yyyy = date_obj.year

    compact = f"{dd}{mm}{yyyy}"
    padded = f"{dd:02d}{mm:02d}{yyyy}"

    base = "https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini"
    out = [
        f"{base}/{compact}.pdf",
        f"{base}/{padded}.pdf",
    ]

    deduped = []
    seen = set()
    for u in out:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def url_exists(url: str, timeout: int = 20) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            return False
        content_type = r.headers.get("Content-Type", "").lower()
        return "pdf" in content_type or url.lower().endswith(".pdf")
    except requests.RequestException:
        return False


def trova_pdf_camera(max_giorni: int = MAX_LOOKBACK_DAYS) -> str:
    oggi = datetime.now()

    for i in range(1, max_giorni + 1):
        data = oggi - timedelta(days=i)
        for url in candidate_camera_urls(data):
            print(f"Tento: {url}")
            if url_exists(url):
                print(f"Trovato PDF: {url}")
                return url

    raise RuntimeError("Nessun PDF trovato negli ultimi giorni")


def scarica_pdf(url: str, output_path: str) -> None:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(r.content)


# =========================================================
# OPENAI ANALISI
# =========================================================
def call_openai_analysis(rules: Dict[str, Any], pdf_text: str) -> Dict[str, Any]:
    api_key = os.environ.get(OPENAI_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"Variabile ambiente mancante: {OPENAI_API_KEY_ENV}")

    client = OpenAI(api_key=api_key)

    today_str = datetime.now().strftime("%Y-%m-%d")
    user_prompt = USER_PROMPT_TEMPLATE.format(
        today=today_str,
        rules_json=json.dumps(rules, ensure_ascii=False, indent=2),
        text=pdf_text,
    )

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    raw = getattr(response, "output_text", "") or ""
    raw = raw.strip()

    if not raw:
        raise RuntimeError("Risposta OpenAI vuota")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON AI non valido: {e.msg}") from e

    if not isinstance(parsed, dict):
        raise RuntimeError("Output AI non valido: atteso oggetto JSON")

    if "atti_rilevanti" not in parsed or not isinstance(parsed["atti_rilevanti"], list):
        raise RuntimeError("Output AI non valido: manca 'atti_rilevanti'")

    return parsed


# =========================================================
# LINK DOCUMENTI
# =========================================================
def normalize_atto_numero(atto_numero: str) -> str:
    return normalize_text(atto_numero)


def build_camera_document_link(atto_numero: str, fallback_pdf_url: str) -> str:
    """
    Costruisce link Camera al documento effettivo quando possibile.
    Se non riconosce il formato, usa il bollettino PDF.
    """
    a = normalize_atto_numero(atto_numero)

    if not a:
        return fallback_pdf_url

    # C. 2855
    m = re.fullmatch(r"C\.\s*([0-9]+[A-Z\-]*)", a, flags=re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"https://www.camera.it/leg19/126?tab=&leg=19&idDocumento={num}"

    # S. 123 -> fallback
    m = re.fullmatch(r"S\.\s*([0-9]+[A-Z\-]*)", a, flags=re.IGNORECASE)
    if m:
        return fallback_pdf_url

    # Atto n. 392
    m = re.fullmatch(r"Atto\s*n\.?\s*([0-9]+)", a, flags=re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"https://www.camera.it/leg19/682?atto={num}"

    m = re.fullmatch(r"atto\s*n\.?\s*([0-9]+)", a, flags=re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"https://www.camera.it/leg19/682?atto={num}"

    # Doc. LXXXVI, n. 4 -> non facile da ricostruire in modo affidabile
    # Interrogazioni / risoluzioni 7-00269, 5-04837 -> fallback
    return fallback_pdf_url


# =========================================================
# PULIZIA / DEDUP / FILTRI
# =========================================================
def clean_organo(organo: str) -> str:
    organo = normalize_text(organo)

    organo = re.sub(r"\(\*\)", "", organo).strip()
    organo = re.sub(r"\s+", " ", organo).strip()

    # elimina pezzi chiaramente sporchi
    organo = re.sub(r"^Alla\s+[IVXLC]+\s+Commissione:\s*", "", organo, flags=re.IGNORECASE)
    organo = re.sub(r"^Rel\.[^)]*\)\s*", "", organo, flags=re.IGNORECASE)
    organo = re.sub(r"^XII Commissione:[^)]*\)\s*", "", organo, flags=re.IGNORECASE)

    # taglia se contiene "Ore ..."
    organo = re.sub(r"\bOre\s+\d.*$", "", organo, flags=re.IGNORECASE).strip()

    # mantieni solo organi plausibili
    if "COMMISSIONE" in organo.upper():
        return organo

    if organo.upper().startswith("COMMISSIONI RIUNITE"):
        return organo

    return organo


def act_key(item: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        normalize_for_compare(item.get("data_riunione", "")),
        normalize_for_compare(item.get("organo", "")),
        normalize_for_compare(item.get("atto_numero", "")),
    )


def payload_signature(item: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        normalize_for_compare(item.get("categoria", "")),
        normalize_for_compare(item.get("motivazione", "")),
        normalize_for_compare("; ".join(item.get("parole_chiave", []))),
    )


def dedupe_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()

    for item in items:
        key = act_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def filter_only_today_or_future(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    today = datetime.now().date()
    out = []

    for item in items:
        d = parse_date_it(item.get("data_riunione", ""))
        if d is None:
            continue
        if d >= today:
            out.append(item)

    return out


def sanitize_ai_items(ai_data: Dict[str, Any], pdf_url: str) -> List[Dict[str, Any]]:
    raw_items = ai_data.get("atti_rilevanti", [])
    cleaned: List[Dict[str, Any]] = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        data_riunione = normalize_text(item.get("data_riunione", ""))
        organo = clean_organo(item.get("organo", ""))
        categoria = normalize_text(item.get("categoria", ""))
        atto_numero = normalize_text(item.get("atto_numero", ""))
        motivazione = normalize_text(item.get("motivazione", ""))
        scadenza = normalize_text(item.get("scadenza_emendamenti", ""))

        parole = item.get("parole_chiave", [])
        if not isinstance(parole, list):
            parole = []
        parole = [normalize_text(x) for x in parole if isinstance(x, str) and normalize_text(x)]

        if categoria not in ALLOWED_CATEGORIES:
            continue
        if not data_riunione or not organo:
            continue

        link_documento = build_camera_document_link(atto_numero, pdf_url)

        cleaned.append(
            {
                "data_riunione": data_riunione,
                "organo": organo,
                "categoria": categoria,
                "atto_numero": atto_numero if atto_numero else "non rilevato",
                "link_documento": link_documento,
                "motivazione": motivazione if motivazione else "",
                "parole_chiave": parole,
                "scadenza_emendamenti": scadenza if scadenza else "non rilevata",
            }
        )

    cleaned = filter_only_today_or_future(cleaned)
    cleaned = dedupe_items(cleaned)
    return cleaned


# =========================================================
# DIFF CON RUN PRECEDENTE
# =========================================================
def load_previous_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"atti_rilevanti": []}
    return load_json_file(STATE_FILE)


def compute_diff(
    previous_items: List[Dict[str, Any]],
    current_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    prev_map = {act_key(x): x for x in previous_items}
    curr_map = {act_key(x): x for x in current_items}

    changes: List[Dict[str, Any]] = []

    for key, curr in curr_map.items():
        prev = prev_map.get(key)

        if prev is None:
            c = deepcopy(curr)
            c["_change_type"] = "NUOVO"
            changes.append(c)
            continue

        if payload_signature(prev) != payload_signature(curr):
            c = deepcopy(curr)
            c["_change_type"] = "MODIFICATO"
            changes.append(c)

    return changes


# =========================================================
# EMAIL
# =========================================================
def motivazione_for_mail(item: Dict[str, Any]) -> str:
    parole = item.get("parole_chiave", [])
    if parole:
        return "; ".join(parole)

    motivazione = normalize_text(item.get("motivazione", ""))
    return motivazione if motivazione else "non rilevata"


def build_email_body(pdf_url: str, items: List[Dict[str, Any]]) -> str:
    grouped = {
        CATEGORY_MARITTIMO: [],
        CATEGORY_TRASPORTO: [],
        CATEGORY_INDUSTRIA: [],
    }

    for item in items:
        cat = item.get("categoria")
        if cat in grouped:
            grouped[cat].append(item)

    body = "MONITOR CAMERA – ANALISI COMPLETA PDF\n\n"
    body += f"Fonte PDF: {pdf_url}\n\n"

    for category in [CATEGORY_MARITTIMO, CATEGORY_TRASPORTO, CATEGORY_INDUSTRIA]:
        section_items = grouped[category]
        if not section_items:
            continue

        body += f"{category}\n\n"

        for item in section_items:
            body += f"Data riunione: {item.get('data_riunione', '')}\n"
            body += f"Organo: {item.get('organo', '')}\n"
            body += f"Atto: {item.get('atto_numero', 'non rilevato')}\n"
            body += f"Link documento: {item.get('link_documento', pdf_url)}\n"
            body += f"Motivazione: {motivazione_for_mail(item)}\n"
            body += f"Scadenza emendamenti: {item.get('scadenza_emendamenti', 'non rilevata')}\n"
            body += "\n---\n\n"

    return body


def send_email(subject: str, body: str) -> None:
    email_user = os.environ.get(EMAIL_USER_ENV)
    email_pass = os.environ.get(EMAIL_PASS_ENV)
    email_to = os.environ.get(EMAIL_TO_ENV)

    print("DEBUG EMAIL:")
    print("USER presente:", bool(email_user))
    print("PASS presente:", bool(email_pass))
    print("TO presente:", bool(email_to))

    if not email_user or not email_pass or not email_to:
        raise RuntimeError(
            f"Secret mancanti. Servono {EMAIL_USER_ENV}, {EMAIL_PASS_ENV}, {EMAIL_TO_ENV}"
        )

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = email_to

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(email_user, email_pass)
        server.sendmail(email_user, [email_to], msg.as_string())

    print("Email inviata")


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    ensure_dir(STATE_DIR)

    rules = load_json_file(RULES_FILE)
    pdf_url = trova_pdf_camera()
    scarica_pdf(pdf_url, PDF_LOCAL_PATH)

    pdf_text = extract_text(PDF_LOCAL_PATH)
    pdf_text = normalize_text(pdf_text)
    
    if not pdf_text:
        raise RuntimeError("Testo PDF vuoto")
    
    # DEBUG (fondamentale)
    if "salario minimo" in pdf_text.lower():
        print("DEBUG: 'salario minimo' trovato nel PDF")
        
    ai_data = call_openai_analysis(rules, pdf_text)
    current_items = sanitize_ai_items(ai_data, pdf_url)

    previous_state = load_previous_state()
    previous_items = previous_state.get("atti_rilevanti", [])
    if not isinstance(previous_items, list):
        previous_items = []

    changed_items = compute_diff(previous_items, current_items)

    if not changed_items:
        print("Nessuna variazione rilevante rispetto al run precedente.")
    else:
        body = build_email_body(pdf_url, changed_items)
        print(body)
        send_email("Monitor Camera", body)

    save_json_file(
        STATE_FILE,
        {
            "last_pdf_url": pdf_url,
            "saved_at": datetime.now().isoformat(),
            "atti_rilevanti": current_items,
        },
    )


if __name__ == "__main__":
    main()