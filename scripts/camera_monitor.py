import json
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

import requests
from pdfminer.high_level import extract_text


# =========================================================
# CONFIG
# =========================================================
RULES_FILE = os.path.join(os.getcwd(), "config", "senato_monitor_rules.json")
PDF_LOCAL_PATH = "camera.pdf"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

EMAIL_USER_ENV = "EMAIL_USER"
EMAIL_PASS_ENV = "EMAIL_PASS"
EMAIL_TO_ENV = "EMAIL_TO"

MAX_LOOKBACK_DAYS = 10
PROXIMITY_WINDOW = 10

CATEGORY_MARITTIMO = "INTERESSE TRASPORTO MARITTIMO"
CATEGORY_TRASPORTO = "INTERESSE INDUSTRIA DEL TRASPORTO"
CATEGORY_INDUSTRIA = "INTERESSE INDUSTRIALE GENERALE"


# =========================================================
# PAROLE A RISCHIO FALSO POSITIVO
# per queste serve vicinanza con: marittimo/marittima/marittime/navigazione
# salvo la parola "navigazione" stessa
# =========================================================
RISKY_TERMS = {
    "porto",
    "porti",
    "portuale",
    "portualità",
    "logistica",
    "trasporti",
    "trasporto merci",
    "pot",
    "pcs",
    "psc",
    "smart port",
    "approdo",
    "rimorchio",
    "pilotaggio",
    "ormeggio",
    "nave",
    "navi",
    "armamento",
    "disarmo",
    "digitalizzazione",
    "innovazione",
    "salute e sicurezza",
    "mit",
    "ram",
    "rina",
    "espo",
    "ustr",
}

MARITIME_ANCHORS = {
    "marittimo",
    "marittima",
    "marittime",
    "navigazione",
}


# =========================================================
# UTILS TESTO
# =========================================================
def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = text.replace("’", "'")
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_match(text: str) -> str:
    text = text.lower()
    text = text.replace("\xa0", " ")
    text = text.replace("’", "'")
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> List[str]:
    return re.findall(r"\b[\w/.-]+\b", text.lower())


def contains_phrase(text_norm: str, phrase: str) -> bool:
    phrase_norm = normalize_for_match(phrase)
    if not phrase_norm:
        return False
    return phrase_norm in text_norm


def proximity_match(text: str, term: str, anchors: set[str], window: int = 10) -> bool:
    """
    Verifica se 'term' compare entro N parole da uno degli anchor.
    """
    text_norm = normalize_for_match(text)
    tokens = tokenize(text_norm)
    term_tokens = tokenize(term)
    if not term_tokens:
        return False

    anchor_positions: List[int] = []
    for i, tok in enumerate(tokens):
        if tok in anchors:
            anchor_positions.append(i)

    if not anchor_positions:
        return False

    term_len = len(term_tokens)
    term_positions: List[int] = []

    for i in range(len(tokens) - term_len + 1):
        if tokens[i:i + term_len] == term_tokens:
            term_positions.append(i)

    for tp in term_positions:
        for ap in anchor_positions:
            if abs(tp - ap) <= window:
                return True

    return False


def is_risky_term(term: str) -> bool:
    return normalize_for_match(term) in RISKY_TERMS


def term_passes_filter(text: str, term: str) -> bool:
    term_norm = normalize_for_match(term)

    if term_norm == "navigazione":
        return contains_phrase(normalize_for_match(text), term_norm)

    if is_risky_term(term_norm):
        return proximity_match(text, term_norm, MARITIME_ANCHORS, PROXIMITY_WINDOW)

    return contains_phrase(normalize_for_match(text), term_norm)


# =========================================================
# LOAD RULES
# =========================================================
def load_rules(path: str) -> Dict[str, Any]:
    print(f"Uso file regole: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Il file JSON delle regole non è valido: riga {e.lineno}, colonna {e.colno}. "
            f"Errore: {e.msg}"
        ) from e
    except FileNotFoundError as e:
        raise RuntimeError(f"File regole non trovato: {path}") from e


def flatten_confitarma_keywords(confitarma_kb: Dict[str, Any]) -> List[str]:
    out: List[str] = []

    keywords = confitarma_kb.get("keywords", {})
    for _, values in keywords.items():
        if isinstance(values, list):
            for v in values:
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())

    keyphrases = confitarma_kb.get("keyphrases", [])
    for v in keyphrases:
        if isinstance(v, str) and v.strip():
            out.append(v.strip())

    programs_tools = confitarma_kb.get("programs_tools", [])
    for v in programs_tools:
        if isinstance(v, str) and v.strip():
            out.append(v.strip())

    entities = confitarma_kb.get("entities", [])
    for v in entities:
        if isinstance(v, str) and v.strip():
            out.append(v.strip())

    norm_refs = confitarma_kb.get("norm_refs", {})
    for _, values in norm_refs.items():
        if isinstance(values, list):
            for v in values:
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())

    return out


def build_rule_sets(rules: Dict[str, Any]) -> Dict[str, Any]:
    excluded_organs = [
        normalize_for_match(x)
        for x in rules.get("excluded_organs", [])
        if isinstance(x, str) and x.strip()
    ]

    resoconto_keywords = [
        x.strip()
        for x in rules.get("resoconto_keywords", [])
        if isinstance(x, str) and x.strip()
    ]

    normative_patterns: List[Tuple[str, str]] = []
    for item in rules.get("normative_patterns", []):
        label = item.get("label", "").strip()
        patterns = item.get("patterns", [])
        if label and isinstance(patterns, list):
            for p in patterns:
                if isinstance(p, str) and p.strip():
                    normative_patterns.append((label, p.strip()))

    confitarma_kb = rules.get("confitarma_kb", {})
    confitarma_keywords = flatten_confitarma_keywords(confitarma_kb)

    return {
        "excluded_organs": excluded_organs,
        "resoconto_keywords": resoconto_keywords,
        "normative_patterns": normative_patterns,
        "confitarma_keywords": confitarma_keywords,
    }


# =========================================================
# TROVA PDF CAMERA
# =========================================================
def candidate_camera_urls(date_obj: datetime) -> List[str]:
    dd = date_obj.day
    mm = date_obj.month
    yyyy = date_obj.year

    compact = f"{dd}{mm}{yyyy}"       # es. 642026
    padded = f"{dd:02d}{mm:02d}{yyyy}"  # es. 06042026

    base = "https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini"

    urls = [
        f"{base}/{compact}.pdf",
        f"{base}/{padded}.pdf",
    ]

    # evita duplicati quando il formato coincide
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def url_exists(url: str, timeout: int = 15) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200 and "application/pdf" in r.headers.get("Content-Type", "").lower()
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


# =========================================================
# DOWNLOAD PDF
# =========================================================
def scarica_pdf(url: str, output_path: str) -> None:
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(r.content)


# =========================================================
# PARSING EVENTI
# =========================================================
def parse_eventi(text: str) -> List[Dict[str, str]]:
    righe_raw = text.splitlines()
    righe = [r.strip() for r in righe_raw if r.strip()]

    pattern_data = re.compile(
        r"^(Lunedì|Martedì|Mercoledì|Giovedì|Venerdì|Sabato|Domenica)\s+\d{1,2}\s+\w+\s+\d{4}",
        re.IGNORECASE,
    )
    pattern_ora = re.compile(r"^Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)", re.IGNORECASE)
    pattern_commissione = re.compile(r"^[IVXLC]+\s+COMMISSIONE", re.IGNORECASE)

    eventi: List[Dict[str, str]] = []
    data_corrente = ""
    commissione_corrente = ""
    evento_corrente: Optional[Dict[str, str]] = None

    for riga in righe:
        riga_norm = normalize_text(riga)

        if pattern_data.match(riga_norm):
            data_corrente = riga_norm
            continue

        if pattern_commissione.search(riga_norm):
            commissione_corrente = riga_norm
            continue

        m_ora = pattern_ora.match(riga_norm)
        if m_ora:
            if evento_corrente:
                eventi.append(evento_corrente)

            evento_corrente = {
                "data": data_corrente,
                "ora": m_ora.group(1),
                "commissione": commissione_corrente,
                "testo": riga_norm,
            }
            continue

        if evento_corrente:
            evento_corrente["testo"] += " " + riga_norm

    if evento_corrente:
        eventi.append(evento_corrente)

    return eventi


# =========================================================
# FILTRI
# =========================================================
def is_excluded_organ(organo: str, excluded_organs: List[str]) -> bool:
    organo_norm = normalize_for_match(organo)
    if not organo_norm:
        return False

    for excl in excluded_organs:
        if excl in organo_norm:
            return True
    return False


# =========================================================
# MATCH REGOLE
# =========================================================
def match_rules(text: str, rule_sets: Dict[str, Any]) -> Tuple[List[str], int]:
    reasons: List[str] = []
    score = 0
    text_norm = normalize_for_match(text)

    # resoconto keywords
    for kw in rule_sets["resoconto_keywords"]:
        if term_passes_filter(text, kw):
            reasons.append(f"keyword:{kw}")
            score += 3

    # confitarma keywords
    for kw in rule_sets["confitarma_keywords"]:
        if term_passes_filter(text, kw):
            reasons.append(f"confitarma_keyword:{kw}")
            score += 2

    # normative patterns
    for label, pattern in rule_sets["normative_patterns"]:
        try:
            if re.search(pattern, text_norm, flags=re.IGNORECASE):
                reasons.append(f"norma:{label}")
                score += 4
        except re.error:
            # fallback se il pattern non è regex valida
            if pattern.lower() in text_norm:
                reasons.append(f"norma:{label}")
                score += 4

    # dedup
    deduped = []
    seen = set()
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped.append(r)

    return deduped, score


# =========================================================
# CLASSIFICAZIONE
# =========================================================
def assegna_categoria(evento: Dict[str, str], reasons: List[str]) -> Optional[str]:
    text = normalize_for_match(evento.get("testo", "") + " " + evento.get("commissione", ""))

    # 1) marittimo
    if any(tag.startswith("keyword:") for tag in reasons):
        return CATEGORY_MARITTIMO

    if any(
        x in text for x in [
            "marittimo",
            "marittima",
            "marittime",
            "navigazione",
            "autorità di sistema portuale",
            "codice della navigazione",
            "demanio marittimo",
            "economia del mare",
            "trasporto marittimo",
            "lavoro marittimo",
            "portuale",
            "portualità",
        ]
    ):
        return CATEGORY_MARITTIMO

    # 2) trasporto generale
    if any(
        x in text for x in [
            "trasporti",
            "trasporto",
            "mobilità",
            "logistica",
            "intermodalità",
            "infrastrutture",
        ]
    ):
        return CATEGORY_TRASPORTO

    # 3) industria generale
    if any(
        x in text for x in [
            "pnrr",
            "decarbonizzazione",
            "energia",
            "industria",
            "innovazione",
            "fit for 55",
            "eu ets",
            "fueleu",
        ]
    ):
        return CATEGORY_INDUSTRIA

    # se non classificabile ma c'è almeno una reason forte normativa
    if any(r.startswith("norma:") for r in reasons):
        return CATEGORY_MARITTIMO

    return None


# =========================================================
# ESTRAZIONI CAMPI MAIL
# =========================================================
def extract_numero_atto(testo: str) -> str:
    patterns = [
        r"\bAtto\s+n\.?\s*\d+\b",
        r"\batto\s+n\.?\s*\d+\b",
        r"\bC\.\s*\d+[A-Z\-]*\b",
        r"\bS\.\s*\d+[A-Z\-]*\b",
        r"\bDoc\.\s*LXXXVI,\s*n\.?\s*\d+\b",
        r"\b7-\d+\b",
        r"\b5-\d+\b",
        r"\bDL\s+\d+/\d{4}\b",
    ]

    testo_norm = normalize_text(testo)

    for pattern in patterns:
        m = re.search(pattern, testo_norm, flags=re.IGNORECASE)
        if m:
            return m.group(0).strip()

    return "non rilevato"


def extract_scadenza_emendamenti(testo: str) -> str:
    testo_norm = normalize_text(testo)

    patterns = [
        r"Entro le ore [^.]+",
        r"Il termine per la presentazione[^.]+",
        r"termine per la presentazione[^.]+",
    ]

    for pattern in patterns:
        m = re.search(pattern, testo_norm, flags=re.IGNORECASE)
        if m:
            return m.group(0).strip()

    return "non rilevata"


def format_motivazione(reasons: List[str]) -> str:
    if not reasons:
        return "nessuna parola chiave trovata"

    valori = []
    seen = set()

    for r in reasons:
        if ":" in r:
            _, val = r.split(":", 1)
        else:
            val = r

        val = val.strip()
        if val and val not in seen:
            seen.add(val)
            valori.append(val)

    return "; ".join(valori) if valori else "nessuna parola chiave trovata"


# =========================================================
# COSTRUZIONE EMAIL
# =========================================================
def build_email(pdf_url: str, eventi: List[Dict[str, Any]]) -> str:
    categorie: Dict[str, List[Dict[str, Any]]] = {
        CATEGORY_MARITTIMO: [],
        CATEGORY_TRASPORTO: [],
        CATEGORY_INDUSTRIA: [],
    }

    for e in eventi:
        cat = e.get("categoria")
        if cat in categorie:
            categorie[cat].append(e)

    body = "MONITOR CAMERA – ANALISI COMPLETA PDF\n\n"
    body += f"Fonte PDF: {pdf_url}\n\n"

    for categoria, items in categorie.items():
        if not items:
            continue

        body += f"{categoria}\n\n"

        for e in items:
            numero_atto = extract_numero_atto(e.get("testo", ""))
            scadenza = extract_scadenza_emendamenti(e.get("testo", ""))
            motivazione = format_motivazione(e.get("reasons", []))

            data_riunione = e.get("data", "") or "non rilevata"
            organo = e.get("commissione", "") or "non rilevato"

            body += f"Data riunione: {data_riunione}\n"
            body += f"Organo: {organo}\n"
            body += f"Atto: {numero_atto}\n"
            body += f"Link documento: {pdf_url}\n"
            body += f"Motivazione: {motivazione}\n"
            body += f"Scadenza emendamenti: {scadenza}\n"
            body += "\n---\n\n"

    return body


# =========================================================
# INVIO EMAIL
# =========================================================
def send_email(body: str) -> None:
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
    msg["Subject"] = "Monitor Camera"
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
    rules = load_rules(RULES_FILE)
    rule_sets = build_rule_sets(rules)

    pdf_url = trova_pdf_camera()
    scarica_pdf(pdf_url, PDF_LOCAL_PATH)

    text = extract_text(PDF_LOCAL_PATH)
    if not text or not text.strip():
        raise RuntimeError("Il testo del PDF risulta vuoto")

    eventi = parse_eventi(text)
    if not eventi:
        raise RuntimeError("Nessun evento estratto dal PDF")

    eventi_finali: List[Dict[str, Any]] = []

    for e in eventi:
        commissione = e.get("commissione", "")

        if is_excluded_organ(commissione, rule_sets["excluded_organs"]):
            continue

        reasons, score = match_rules(e.get("testo", ""), rule_sets)
        categoria = assegna_categoria(e, reasons)

        if categoria and reasons:
            e["reasons"] = reasons
            e["score"] = score
            e["categoria"] = categoria
            eventi_finali.append(e)

    if not eventi_finali:
        body = (
            "MONITOR CAMERA – ANALISI COMPLETA PDF\n\n"
            f"Fonte PDF: {pdf_url}\n\n"
            "Nessun evento rilevante trovato.\n"
        )
    else:
        body = build_email(pdf_url, eventi_finali)

    print(body)
    send_email(body)


if __name__ == "__main__":
    main()