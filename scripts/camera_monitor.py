import requests
import re
import json
import smtplib
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pdfminer.high_level import extract_text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)

PDF_FILE = os.path.join(BASE_DIR, "camera.pdf")
RULES_FILE = os.path.join(REPO_DIR, "config", "senato_monitor_rules.json")


# ---------------------------
# URL PDF CAMERA
# ---------------------------
def build_url(date_obj):
    return (
        "https://documenti.camera.it/_dati/leg19/lavori/Commissioni/"
        f"Bollettini/{date_obj.day}{date_obj.month}{date_obj.year}.pdf"
    )


def is_valid_pdf(response):
    return response.status_code == 200 and response.content[:4] == b"%PDF"


def download_pdf(url):
    try:
        r = requests.get(url, timeout=(15, 90))
        if is_valid_pdf(r):
            return r.content
    except requests.RequestException as e:
        print(f"Errore download {url}: {e}")
    return None


def trova_pdf_camera():
    oggi = datetime.now().date()

    monday_current = oggi - timedelta(days=oggi.weekday())
    monday_previous = monday_current - timedelta(days=7)

    giorni_corrente = [
        monday_current + timedelta(days=i)
        for i in range((oggi - monday_current).days + 1)
    ]

    giorni_precedente = [
        monday_previous + timedelta(days=i)
        for i in range(5)
    ]

    candidati = giorni_corrente + giorni_precedente

    for data in candidati:
        url = build_url(data)
        print(f"Tento: {url}")
        content = download_pdf(url)
        if content:
            print(f"Trovato PDF: {url}")
            return url, content

    raise RuntimeError("Nessun PDF trovato")


# ---------------------------
# REGOLE
# ---------------------------
def load_rules(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def flatten_confitarma_keywords(confitarma_keywords):
    out = []
    for values in confitarma_keywords.values():
        out.extend(values)
    return out


def compile_rules(rules):
    excluded_organs = [
        x.lower().strip()
        for x in rules.get("excluded_organs", [])
    ]

    resoconto_keywords = [
        x.lower().strip()
        for x in rules.get("resoconto_keywords", [])
    ]

    normative_patterns = []
    for item in rules.get("normative_patterns", []):
        for pat in item.get("patterns", []):
            normative_patterns.append(re.compile(pat, re.IGNORECASE))

    confitarma = rules.get("confitarma_kb", {})

    confitarma_keywords = [
        x.lower().strip()
        for x in flatten_confitarma_keywords(confitarma.get("keywords", {}))
    ]

    keyphrases = [
        x.lower().strip()
        for x in confitarma.get("keyphrases", [])
    ]

    norm_refs = []
    for values in confitarma.get("norm_refs", {}).values():
        norm_refs.extend([x.lower().strip() for x in values])

    programs_tools = [
        x.lower().strip()
        for x in confitarma.get("programs_tools", [])
    ]

    entities = [
        x.lower().strip()
        for x in confitarma.get("entities", [])
    ]

    return {
        "excluded_organs": excluded_organs,
        "resoconto_keywords": resoconto_keywords,
        "normative_patterns": normative_patterns,
        "confitarma_keywords": confitarma_keywords,
        "keyphrases": keyphrases,
        "norm_refs": norm_refs,
        "programs_tools": programs_tools,
        "entities": entities,
    }


# ---------------------------
# TESTO / MATCH
# ---------------------------
def pulisci_testo(t):
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def norm_text(s):
    return " ".join(s.lower().split())


def literal_pattern(term):
    term = norm_text(term)
    escaped = re.escape(term)
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def build_literal_patterns(compiled_rules):
    compiled_rules["resoconto_keyword_patterns"] = [
        (kw, literal_pattern(kw))
        for kw in compiled_rules["resoconto_keywords"]
        if len(norm_text(kw)) >= 3
    ]

    compiled_rules["confitarma_keyword_patterns"] = [
        (kw, literal_pattern(kw))
        for kw in compiled_rules["confitarma_keywords"]
        if len(norm_text(kw)) >= 4
    ]

    compiled_rules["keyphrase_patterns"] = [
        (kp, literal_pattern(kp))
        for kp in compiled_rules["keyphrases"]
        if len(norm_text(kp)) >= 4
    ]

    compiled_rules["norm_ref_patterns"] = [
        (nr, literal_pattern(nr))
        for nr in compiled_rules["norm_refs"]
        if len(norm_text(nr)) >= 4
    ]

    compiled_rules["program_patterns"] = [
        (pg, literal_pattern(pg))
        for pg in compiled_rules["programs_tools"]
        if len(norm_text(pg)) >= 3
    ]

    # per entities: tengo solo quelle abbastanza specifiche
    compiled_rules["entity_patterns"] = [
        (ent, literal_pattern(ent))
        for ent in compiled_rules["entities"]
        if len(norm_text(ent)) >= 4
    ]

    return compiled_rules


def collect_match_reasons(text, commissione, compiled_rules):
    haystack = norm_text(f"{commissione}\n{text}")
    reasons = []
    score = 0

    for kw, rx in compiled_rules["resoconto_keyword_patterns"]:
        if rx.search(haystack):
            reasons.append(f"keyword:{kw}")
            score += 3

    for kw, rx in compiled_rules["confitarma_keyword_patterns"]:
        if rx.search(haystack):
            reasons.append(f"confitarma_keyword:{kw}")
            score += 3

    for kp, rx in compiled_rules["keyphrase_patterns"]:
        if rx.search(haystack):
            reasons.append(f"keyphrase:{kp}")
            score += 4

    for nr, rx in compiled_rules["norm_ref_patterns"]:
        if rx.search(haystack):
            reasons.append(f"norm_ref:{nr}")
            score += 4

    for ent, rx in compiled_rules["entity_patterns"]:
        if rx.search(haystack):
            reasons.append(f"entity:{ent}")
            score += 2

    for pg, rx in compiled_rules["program_patterns"]:
        if rx.search(haystack):
            reasons.append(f"program:{pg}")
            score += 2

    raw_text = f"{commissione}\n{text}"
    for rx in compiled_rules["normative_patterns"]:
        if rx.search(raw_text):
            reasons.append(f"normative_pattern:{rx.pattern}")
            score += 4

    seen = set()
    unique = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    return unique, score


def evento_rilevante(evento, compiled_rules):
    if is_excluded_organ(evento["commissione"], compiled_rules):
        return False, [], 0

    reasons, score = collect_match_reasons(
        evento["testo"],
        evento["commissione"],
        compiled_rules
    )

    # mostra solo blocchi con almeno una vera densità tematica
    if score >= 4:
        return True, reasons, score

    return False, reasons, score

# ---------------------------
# PARSING PDF
# ---------------------------
def parse_camera_pdf_text(text):
    text = re.sub(r"-\s*\d+\s*-", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    righe = [r.strip() for r in text.splitlines() if r.strip()]

    pattern_commissione = re.compile(r"^[IVXLC]+\s+COMMISSIONE\s+PERMANENTE.*")
    pattern_data = re.compile(
        r"^(Lunedì|Martedì|Mercoledì|Giovedì|Venerdì|Sabato)\s+\d{1,2}\s+\w+\s+\d{4}$"
    )
    pattern_ora = re.compile(r"^Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)\b")

    eventi = []
    commissione_corrente = ""
    data_corrente = ""
    evento_corrente = None

    for riga in righe:
        if pattern_commissione.match(riga):
            commissione_corrente = riga
            continue

        if pattern_data.match(riga):
            data_corrente = riga
            continue

        m_ora = pattern_ora.match(riga)
        if m_ora:
            if evento_corrente:
                evento_corrente["testo"] = pulisci_testo(evento_corrente["testo"])
                eventi.append(evento_corrente)

            evento_corrente = {
                "commissione": commissione_corrente,
                "data": data_corrente,
                "ora": m_ora.group(1).replace(",", "."),
                "testo": riga,
            }
            continue

        if evento_corrente:
            evento_corrente["testo"] += "\n" + riga

    if evento_corrente:
        evento_corrente["testo"] = pulisci_testo(evento_corrente["testo"])
        eventi.append(evento_corrente)

    return eventi


# ---------------------------
# EMAIL
# ---------------------------
def build_email_body(pdf_url, eventi_rilevanti):
    body = "MONITOR CAMERA – EVENTI RILEVANTI\n\n"
    body += f"Fonte PDF: {pdf_url}\n\n"

    if not eventi_rilevanti:
        body += "Nessun evento rilevante trovato.\n"
        return body

    for e in eventi_rilevanti:
        body += f"{e['data']} - {e['ora']} | {e['commissione']}\n"
        body += e["testo"][:1200] + "\n"
        body += "Match: " + ", ".join(e["match_reasons"][:10]) + "\n"
        body += "\n---\n\n"

    return body


def send_email(subject, body):
    to_email = os.environ.get("EMAIL_TO", os.environ["EMAIL_USER"])

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = os.environ["EMAIL_USER"]
    msg["To"] = to_email

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
        server.sendmail(
            os.environ["EMAIL_USER"],
            [to_email],
            msg.as_string()
        )

    print(f"Email inviata a: {to_email}")


# ---------------------------
# MAIN
# ---------------------------
def main():
    print(f"Uso file regole: {RULES_FILE}")

    rules = load_rules(RULES_FILE)
    compiled_rules = compile_rules(rules)

    pdf_url, pdf_content = trova_pdf_camera()

    with open(PDF_FILE, "wb") as f:
        f.write(pdf_content)

    text = extract_text(PDF_FILE)
    eventi = parse_camera_pdf_text(text)

    compiled_rules = build_literal_patterns(compiled_rules)

    eventi_rilevanti = []
    for e in eventi:
        ok, reasons, score = evento_rilevante(e, compiled_rules)
        if ok:
            e["match_reasons"] = reasons
            e["score"] = score
            eventi_rilevanti.append(e)
    body = build_email_body(pdf_url, eventi_rilevanti)
    send_email("Monitor Camera - Eventi rilevanti", body)

    print(f"PDF usato: {pdf_url}")
    print(f"Eventi totali: {len(eventi)}")
    print(f"Eventi rilevanti: {len(eventi_rilevanti)}")


if __name__ == "__main__":
    main()