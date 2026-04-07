import json
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

import requests
from pdfminer.high_level import extract_text


# =========================================================
# CONFIG
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent
RULES_FILE = BASE_DIR / "config" / "senato_monitor_rules.json"
PDF_PATH = BASE_DIR / "camera.pdf"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

MAIL_FROM = os.environ.get("EMAIL_USER")
MAIL_PASS = os.environ.get("EMAIL_PASS")
MAIL_TO = os.environ.get("EMAIL_TO")

MAX_LOOKBACK_DAYS = 10
SNIPPET_MAX_LEN = 1600

# Termini che possono generare falsi positivi se presi da soli.
# Per questi, il match vale solo se vicino (±10 parole) a indicatori marittimi.
PROXIMITY_SENSITIVE_TERMS = {
    "porto",
    "porti",
    "trasporti",
    "logistica",
    "pilotaggio",
    "ormeggio",
    "rimorchio",
    "approdo",
    "pot",
    "pcs",
    "sms",
    "nave",
    "navi",
    "armatore",
    "armatori",
    "cabotaggio",
    "digitalizzazione",
    "innovazione",
    "salute e sicurezza",
}

MARITIME_CONTEXT_TERMS = {
    "marittimo",
    "marittima",
    "marittimi",
    "marittime",
    "navigazione",
}

# Questi termini sono abbastanza forti da soli
# e non richiedono il controllo di prossimità.
STRONG_TERMS_ALWAYS_VALID = {
    "autorità di sistema portuale",
    "codice della navigazione",
    "lavoro marittimo",
    "demanio marittimo",
    "economia del mare",
    "autostrade del mare",
    "trasporto marittimo",
    "linee marittime",
    "collegamenti marittimi",
    "sea modal shift",
    "portuale",
    "portualità",
    "sanità marittima",
    "sanità marittima di bordo",
    "sanità di bordo",
    "telemedicina marittima",
    "servizio sanitario di bordo",
    "dotazioni mediche delle navi",
    "gente di mare",
    "documenti di bordo",
    "ordinamento marittimo",
    "impresa di navigazione",
    "compagnie di navigazione",
    "fueleu maritime",
    "ets marittimo",
    "maritime single window",
    "port state control",
    "green shipping corridors",
    "shipping",
    "ship finance",
    "ccnl marittimo",
    "finanza verde nel settore marittimo",
    "regime italiano di aiuti di stato ai trasporti marittimi",
}


# =========================================================
# UTILS TESTO
# =========================================================
def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[‐-–—]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize_words(text: str) -> list[str]:
    return re.findall(r"\b[\w/-]+\b", text.lower(), flags=re.UNICODE)


def find_phrase_positions(tokens: list[str], phrase: str) -> list[int]:
    phrase_tokens = tokenize_words(phrase)
    if not phrase_tokens:
        return []

    positions = []
    span = len(phrase_tokens)

    for i in range(len(tokens) - span + 1):
        if tokens[i:i + span] == phrase_tokens:
            positions.append(i)

    return positions


def has_maritime_context_near(tokens: list[str], phrase: str, window: int = 10) -> bool:
    phrase_tokens = tokenize_words(phrase)
    if not phrase_tokens:
        return False

    positions = find_phrase_positions(tokens, phrase)
    if not positions:
        return False

    for start in positions:
        left = max(0, start - window)
        right = min(len(tokens), start + len(phrase_tokens) + window)
        context = tokens[left:right]

        for ctx in MARITIME_CONTEXT_TERMS:
            if ctx == "navigazione" and phrase == "navigazione":
                return True
            if ctx in context:
                return True

    return False


def phrase_match(text: str, phrase: str) -> bool:
    tokens = tokenize_words(text)
    phrase_l = phrase.lower()

    if phrase_l in STRONG_TERMS_ALWAYS_VALID:
        return bool(find_phrase_positions(tokens, phrase_l))

    if phrase_l == "navigazione":
        return bool(find_phrase_positions(tokens, phrase_l))

    if phrase_l in PROXIMITY_SENSITIVE_TERMS:
        return has_maritime_context_near(tokens, phrase_l, window=10)

    return bool(find_phrase_positions(tokens, phrase_l))


def regex_match(text: str, pattern: str) -> bool:
    try:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    except re.error:
        return False


# =========================================================
# LOAD RULES
# =========================================================
def load_rules(path: Path) -> dict:
    print(f"Uso file regole: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# =========================================================
# PDF CAMERA
# =========================================================
def build_camera_pdf_url(date_obj: datetime) -> str:
    # Formato corretto osservato nei PDF Camera:
    # es. 3032026.pdf per 30/03/2026
    return (
        "https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/"
        f"{date_obj.day}{date_obj.month}{date_obj.year}.pdf"
    )


def trova_pdf_camera(max_giorni: int = MAX_LOOKBACK_DAYS) -> str:
    oggi = datetime.now()

    for i in range(1, max_giorni + 1):
        data = oggi - timedelta(days=i)
        url = build_camera_pdf_url(data)

        try:
            print(f"Tento: {url}")
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and "application/pdf" in r.headers.get("Content-Type", "").lower():
                print(f"Trovato PDF: {url}")
                return url
        except requests.RequestException:
            pass

    raise RuntimeError("Nessun PDF trovato negli ultimi giorni")


def scarica_pdf(url: str, output_path: Path) -> None:
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(r.content)


# =========================================================
# PARSING EVENTI
# =========================================================
def parse_eventi(text: str) -> list[dict]:
    righe = [r.strip() for r in text.splitlines() if r.strip()]

    pattern_data = re.compile(
        r"^(Lunedì|Martedì|Mercoledì|Giovedì|Venerdì|Sabato|Domenica)\s+\d{1,2}\s+\w+\s+\d{4}",
        flags=re.IGNORECASE,
    )
    pattern_ora = re.compile(r"^Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)$", flags=re.IGNORECASE)

    eventi = []
    data_corrente = ""
    commissione_corrente = ""
    evento_corrente = None

    for riga in righe:
        riga_norm = normalize_text(riga)

        if pattern_data.match(riga_norm):
            data_corrente = riga_norm
            continue

        if "COMMISSIONE" in riga_norm.upper() and "INDICE CONVOCAZIONI" not in riga_norm.upper():
            commissione_corrente = riga_norm
            continue

        m_ora = pattern_ora.match(riga_norm)
        if m_ora:
            if evento_corrente:
                eventi.append(evento_corrente)

            evento_corrente = {
                "data": data_corrente,
                "ora": m_ora.group(1).replace(",", "."),
                "commissione": commissione_corrente,
                "testo": f"Ore {m_ora.group(1)}",
            }
            continue

        if evento_corrente:
            evento_corrente["testo"] += "\n" + riga_norm

    if evento_corrente:
        eventi.append(evento_corrente)

    return eventi


# =========================================================
# MATCH REGOLE SENATO
# =========================================================
def iter_confitarma_keywords(rules: dict):
    confitarma = rules.get("confitarma_kb", {})
    keywords = confitarma.get("keywords", {})

    for group_name, terms in keywords.items():
        for term in terms:
            yield group_name, term


def iter_confitarma_keyphrases(rules: dict):
    for phrase in rules.get("confitarma_kb", {}).get("keyphrases", []):
        yield phrase


def iter_confitarma_entities(rules: dict):
    for entity in rules.get("confitarma_kb", {}).get("entities", []):
        yield entity


def iter_programs_tools(rules: dict):
    for item in rules.get("confitarma_kb", {}).get("programs_tools", []):
        yield item


def iter_norm_refs(rules: dict):
    norm_refs = rules.get("confitarma_kb", {}).get("norm_refs", {})
    for area, refs in norm_refs.items():
        for ref in refs:
            yield area, ref


def iter_resoconto_keywords(rules: dict):
    for kw in rules.get("resoconto_keywords", []):
        yield kw


def iter_normative_patterns(rules: dict):
    for item in rules.get("normative_patterns", []):
        label = item.get("label", "")
        patterns = item.get("patterns", [])
        for pattern in patterns:
            yield label, pattern


def match_rules(text: str, rules: dict) -> tuple[list[str], int]:
    text_norm = normalize_text(text).lower()
    reasons = []
    score = 0

    # resoconto_keywords
    for kw in iter_resoconto_keywords(rules):
        if phrase_match(text_norm, kw.lower()):
            reasons.append(f"keyword:{kw}")
            score += 3

    # confitarma keywords
    for _, kw in iter_confitarma_keywords(rules):
        if phrase_match(text_norm, kw.lower()):
            reasons.append(f"confitarma_keyword:{kw}")
            score += 3

    # keyphrases
    for phrase in iter_confitarma_keyphrases(rules):
        if phrase_match(text_norm, phrase.lower()):
            reasons.append(f"keyphrase:{phrase}")
            score += 4

    # entities
    for entity in iter_confitarma_entities(rules):
        if phrase_match(text_norm, entity.lower()):
            reasons.append(f"entity:{entity}")
            score += 2

    # programs/tools
    for item in iter_programs_tools(rules):
        if phrase_match(text_norm, item.lower()):
            reasons.append(f"program:{item}")
            score += 4

    # norm_refs
    for _, ref in iter_norm_refs(rules):
        if phrase_match(text_norm, ref.lower()):
            reasons.append(f"norm_ref:{ref}")
            score += 4

    # normative_patterns
    for label, pattern in iter_normative_patterns(rules):
        if regex_match(text_norm, pattern):
            reasons.append(f"normative:{label}")
            score += 4

    # dedup preservando ordine
    seen = set()
    deduped = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped.append(r)

    return deduped, score


# =========================================================
# CLASSIFICAZIONE
# =========================================================
def assegna_categoria(evento: dict, reasons: list[str]) -> str | None:
    text = normalize_text(f"{evento['commissione']} {evento['testo']}").lower()
    joined = " | ".join(reasons).lower()

    maritime_strong = any(x in joined for x in [
        "keyword:porto",
        "keyword:porti",
        "keyword:portuale",
        "keyword:portualità",
        "keyword:marittimo",
        "keyword:marittima",
        "keyword:navigazione",
        "confitarma_keyword:trasporto marittimo",
        "confitarma_keyword:linee marittime",
        "confitarma_keyword:collegamenti marittimi",
        "confitarma_keyword:cabotaggio",
        "confitarma_keyword:autostrade del mare",
        "confitarma_keyword:sea modal shift",
        "confitarma_keyword:autorità di sistema portuale",
        "confitarma_keyword:port state control",
        "confitarma_keyword:maritime single window",
        "confitarma_keyword:gente di mare",
        "confitarma_keyword:lavoro marittimo",
        "confitarma_keyword:ordinamento marittimo",
        "confitarma_keyword:telemedicina marittima",
        "confitarma_keyword:servizio sanitario di bordo",
        "confitarma_keyword:dotazioni mediche delle navi",
    ])

    if maritime_strong:
        return "INTERESSE TRASPORTO MARITTIMO"

    if any(x in text for x in ["trasporti", "logistica", "mobilità", "intermodalità"]):
        return "INTERESSE INDUSTRIA DEL TRASPORTO"

    if any(x in text for x in ["pnrr", "energia", "decarbonizzazione", "industria"]):
        return "INTERESSE INDUSTRIALE GENERALE"

    if reasons:
        return "INTERESSE INDUSTRIALE GENERALE"

    return None


# =========================================================
# FILTRI ANTIRUMORE
# =========================================================
def is_noise_event(evento: dict, reasons: list[str]) -> bool:
    text = normalize_text(evento["testo"]).lower()
    commissione = normalize_text(evento["commissione"]).lower()
    joined = " | ".join(reasons).lower()

    # se il match è solo su entità generiche, scarta
    if reasons and all(r.startswith("entity:") for r in reasons):
        return True

    # falsi positivi classici su "porto/porti/trasporti"
    if "keyword:porto" in joined or "keyword:porti" in joined or "keyword:trasporti" in joined:
        if not any(x in joined for x in [
            "confitarma_keyword:cabotaggio",
            "confitarma_keyword:trasporto marittimo",
            "confitarma_keyword:linee marittime",
            "confitarma_keyword:collegamenti marittimi",
            "confitarma_keyword:autostrade del mare",
            "confitarma_keyword:sea modal shift",
            "confitarma_keyword:autorità di sistema portuale",
        ]):
            if "capitaneria di porto" not in text and "porto di " not in text:
                if "ministero delle infrastrutture e dei trasporti" in text:
                    return True
                if "commissione ix" in commissione or "trasporti, poste e telecomunicazioni" in commissione:
                    return True

    # eventi puramente procedurali
    procedural_markers = [
        "ufficio di presidenza",
        "comunicazioni del presidente",
        "avviso",
        "i deputati possono partecipare in videoconferenza",
        "la convocazione è stata aggiornata",
        "non sono previste votazioni",
    ]
    if all(marker in text for marker in ["avviso", "videoconferenza"]) and len(reasons) <= 1:
        return True
    if "ufficio di presidenza" in text and len(reasons) <= 1:
        return True
    if "comunicazioni del presidente" in text and len(reasons) <= 1:
        return True

    return False


# =========================================================
# EMAIL
# =========================================================
def snippet(text: str, max_len: int = SNIPPET_MAX_LEN) -> str:
    text = normalize_text(text)
    return text[:max_len].rstrip()


def build_email(pdf_url: str, eventi: list[dict]) -> str:
    categorie = {
        "INTERESSE TRASPORTO MARITTIMO": [],
        "INTERESSE INDUSTRIA DEL TRASPORTO": [],
        "INTERESSE INDUSTRIALE GENERALE": [],
    }

    for e in eventi:
        if e["categoria"] in categorie:
            categorie[e["categoria"]].append(e)

    body = "MONITOR CAMERA – ANALISI COMPLETA PDF\n\n"
    body += f"Fonte PDF: {pdf_url}\n\n"

    for categoria, items in categorie.items():
        if not items:
            continue

        body += f"{categoria}\n\n"

        for e in items:
            body += f"{e['data']} - {e['ora']} | {e['commissione']}\n"
            body += snippet(e["testo"]) + "\n"
            body += f"Score: {e['score']}\n"
            body += f"Match: {', '.join(e['reasons'])}\n"
            body += "\n---\n\n"

    if all(not v for v in categorie.values()):
        body += "Nessun evento rilevante individuato.\n"

    return body


def send_email(subject: str, body: str) -> None:
    if not MAIL_FROM or not MAIL_PASS or not MAIL_TO:
        raise RuntimeError(
            "Variabili EMAIL_USER / EMAIL_PASS / EMAIL_TO mancanti nei secrets."
        )

    print("DEBUG EMAIL:")
    print("FROM:", MAIL_FROM)
    print("TO:", MAIL_TO)

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(MAIL_FROM, MAIL_PASS)
        server.sendmail(MAIL_FROM, [MAIL_TO], msg.as_string())

    print("Email inviata")


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    rules = load_rules(RULES_FILE)

    pdf_url = trova_pdf_camera()
    scarica_pdf(pdf_url, PDF_PATH)

    text = extract_text(str(PDF_PATH))
    if not text.strip():
        raise RuntimeError("Testo PDF vuoto o non estraibile")

    eventi = parse_eventi(text)
    eventi_finali = []

    for e in eventi:
        reasons, score = match_rules(e["testo"], rules)

        if not reasons:
            continue

        if is_noise_event(e, reasons):
            continue

        categoria = assegna_categoria(e, reasons)
        if not categoria:
            continue

        e["reasons"] = reasons
        e["score"] = score
        e["categoria"] = categoria
        eventi_finali.append(e)

    # ordinamento: prima categoria, poi score decrescente, poi data/ora come trovato
    category_order = {
        "INTERESSE TRASPORTO MARITTIMO": 0,
        "INTERESSE INDUSTRIA DEL TRASPORTO": 1,
        "INTERESSE INDUSTRIALE GENERALE": 2,
    }

    eventi_finali.sort(
        key=lambda x: (
            category_order.get(x["categoria"], 99),
            -x["score"],
            x["data"],
            x["ora"],
        )
    )

    body = build_email(pdf_url, eventi_finali)
    print(body)
    send_email("Monitor Camera", body)


if __name__ == "__main__":
    main()