import os
import re
import json
import requests
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pdfminer.high_level import extract_text


# =========================
# CONFIG
# =========================
RULES_FILE = os.path.join(os.getcwd(), "config", "senato_monitor_rules.json")
PDF_FILE = "camera.pdf"


# =========================
# LOAD RULES
# =========================
def load_rules(path):
    print(f"Uso file regole: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def flatten_rules(rules):
    """
    Appiattisce solo le parti utili del file senato_monitor_rules.json
    in liste semplici di keyword/keyphrase/normative/entity/program.
    """
    flattened = {
        "resoconto_keywords": [],
        "normative_patterns": [],
        "confitarma_keywords": [],
        "keyphrases": [],
        "norm_refs_italia": [],
        "norm_refs_ue_int": [],
        "programs_tools": [],
        "entities": [],
    }

    flattened["resoconto_keywords"] = [
        x.lower() for x in rules.get("resoconto_keywords", [])
    ]

    for item in rules.get("normative_patterns", []):
        for p in item.get("patterns", []):
            flattened["normative_patterns"].append((item.get("label", ""), p.lower()))

    confitarma_kb = rules.get("confitarma_kb", {})

    for _, values in confitarma_kb.get("keywords", {}).items():
        for v in values:
            flattened["confitarma_keywords"].append(v.lower())

    flattened["keyphrases"] = [x.lower() for x in confitarma_kb.get("keyphrases", [])]
    flattened["norm_refs_italia"] = [x.lower() for x in confitarma_kb.get("norm_refs", {}).get("italia", [])]
    flattened["norm_refs_ue_int"] = [x.lower() for x in confitarma_kb.get("norm_refs", {}).get("ue_internazionale", [])]
    flattened["programs_tools"] = [x.lower() for x in confitarma_kb.get("programs_tools", [])]
    flattened["entities"] = [x.lower() for x in confitarma_kb.get("entities", [])]

    return flattened


# =========================
# PDF CAMERA
# =========================
def trova_pdf_camera(max_giorni=10):
    """
    La Camera usa URL del tipo:
    3032026.pdf = 30/3/2026
    cioè giorno e mese SENZA zero iniziale.
    """
    oggi = datetime.now()

    for i in range(1, max_giorni + 1):
        data = oggi - timedelta(days=i)
        data_str = f"{data.day}{data.month}{data.year}"

        url = f"https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/{data_str}.pdf"

        try:
            print(f"Tento: {url}")
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                print(f"Trovato PDF: {url}")
                return url
        except requests.RequestException as e:
            print(f"Errore su {url}: {e}")

    raise RuntimeError("Nessun PDF trovato negli ultimi giorni")


def scarica_pdf(url, output_path):
    r = requests.get(url, timeout=60)
    r.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(r.content)


# =========================
# PULIZIA TESTO
# =========================
def normalize_text(text):
    text = text.replace("\xa0", " ")
    text = re.sub(r"-\s*\d+\s*-", "\n", text)  # rimuove numeri pagina tipo - 6 -
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# =========================
# PARSING EVENTI
# =========================
def parse_eventi(text):
    righe = [r.strip() for r in text.splitlines() if r.strip()]

    pattern_data = re.compile(
        r"^(Lunedì|Martedì|Mercoledì|Giovedì|Venerdì|Sabato)\s+\d{1,2}\s+\w+\s+\d{4}(?:\s*\(\*\))?$",
        re.IGNORECASE
    )
    pattern_ora = re.compile(r"^Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)", re.IGNORECASE)
    pattern_commissione = re.compile(r"^[IVXLC]+\s+COMMISSIONE\s+PERMANENTE", re.IGNORECASE)

    stop_patterns = [
        re.compile(r"^I\s*N\s*D\s*I\s*C\s*E", re.IGNORECASE),
        re.compile(r"^Pag\.\s*$", re.IGNORECASE),
        re.compile(r"^Pag\.\s*\d+", re.IGNORECASE),
        re.compile(r"^[IVXLC]+\s+[A-ZÀ-Ú].*\. \. \.$"),
        re.compile(r"^[IVXLC]+\s+[A-ZÀ-Ú].*\.\s*\.\s*\.\s*$"),
    ]

    eventi = []
    data_corrente = ""
    commissione_corrente = ""
    evento_corrente = None

    def chiudi_evento(ev):
        if not ev:
            return None
        testo = ev["testo"]

        righe_ev = []
        for r in testo.splitlines():
            stop = False
            for p in stop_patterns:
                if p.search(r):
                    stop = True
                    break
            if stop:
                break
            righe_ev.append(r)

        ev["testo"] = "\n".join(righe_ev).strip()

        if len(ev["testo"]) < 40:
            return None

        return ev

    for riga in righe:
        if pattern_data.match(riga):
            data_corrente = riga
            continue

        if pattern_commissione.match(riga):
            commissione_corrente = riga
            continue

        m_ora = pattern_ora.match(riga)
        if m_ora:
            chiuso = chiudi_evento(evento_corrente)
            if chiuso:
                eventi.append(chiuso)

            evento_corrente = {
                "data": data_corrente,
                "ora": m_ora.group(1).replace(",", "."),
                "commissione": commissione_corrente,
                "testo": riga
            }
            continue

        if evento_corrente:
            evento_corrente["testo"] += "\n" + riga

    chiuso = chiudi_evento(evento_corrente)
    if chiuso:
        eventi.append(chiuso)

    return eventi

# =========================
# MATCH RULES
# =========================
def match_rules(text, rules_flat):
    text_l = text.lower()
    reasons = []
    score = 0

    # resoconto keywords
    for k in rules_flat["resoconto_keywords"]:
        if k and k in text_l:
            reasons.append(f"keyword:{k}")
            score += 3

    # confitarma keywords
    for k in rules_flat["confitarma_keywords"]:
        if k and k in text_l:
            reasons.append(f"confitarma_keyword:{k}")
            score += 3

    # keyphrases
    for k in rules_flat["keyphrases"]:
        if k and k in text_l:
            reasons.append(f"keyphrase:{k}")
            score += 6

    # norm refs italia
    for k in rules_flat["norm_refs_italia"]:
        if k and k in text_l:
            reasons.append(f"norm_italia:{k}")
            score += 4

    # norm refs ue/int
    for k in rules_flat["norm_refs_ue_int"]:
        if k and k in text_l:
            reasons.append(f"norm_ue_int:{k}")
            score += 4

    # programs
    for k in rules_flat["programs_tools"]:
        if k and k in text_l:
            reasons.append(f"program:{k}")
            score += 2

    # entities
    for k in rules_flat["entities"]:
        if k and k in text_l:
            reasons.append(f"entity:{k}")
            score += 2

    # normative regex patterns
    for label, pattern in rules_flat["normative_patterns"]:
        try:
            if re.search(pattern, text_l, re.IGNORECASE):
                reasons.append(f"norm_pattern:{label}")
                score += 4
        except re.error:
            pass

    # dedup mantenendo ordine
    seen = set()
    dedup = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            dedup.append(r)

    return dedup, score


# =========================
# CLASSIFICAZIONE
# =========================
def assegna_categoria(evento, reasons):
    text = (evento["commissione"] + "\n" + evento["testo"]).lower()

    marittimo_terms_forti = [
        "marittimo", "marittima", "porto", "porti", "portuale",
        "autorità di sistema portuale", "adsp", "navigazione",
        "codice della navigazione", "demanio marittimo",
        "economia del mare", "autostrade del mare", "sea modal shift",
        "shipping", "cabotaggio", "capitaneria di porto", "capitanerie di porto",
        "cold ironing", "shore power", "fueleu", "ets marittimo",
        "mlc 2006", "stcw", "solas", "marpol"
    ]

    trasporto_terms = [
        "trasporti", "trasporto", "logistica", "mobilità", "infrastrutture"
    ]

    generale_terms = [
        "energia", "decarbonizzazione", "pnrr", "industria", "innovazione",
        "cantieristica", "supply chain"
    ]

    if any(t in text for t in marittimo_terms_forti):
        return "INTERESSE TRASPORTO MARITTIMO"

    if any(t in text for t in trasporto_terms):
        return "INTERESSE INDUSTRIA DEL TRASPORTO"

    if any(t in text for t in generale_terms):
        return "INTERESSE INDUSTRIALE GENERALE"

    return None

# =========================
# EMAIL
# =========================
def build_email(pdf_url, eventi):
    categorie = {
        "INTERESSE TRASPORTO MARITTIMO": [],
        "INTERESSE INDUSTRIA DEL TRASPORTO": [],
        "INTERESSE INDUSTRIALE GENERALE": [],
    }

    for e in eventi:
        if e.get("categoria"):
            categorie[e["categoria"]].append(e)

    body = "MONITOR CAMERA – ANALISI COMPLETA PDF\n\n"
    body += f"Fonte PDF: {pdf_url}\n\n"

    vuoto = True

    for cat, items in categorie.items():
        if not items:
            continue

        vuoto = False
        body += f"{cat}\n\n"

        for e in items:
            body += f"{e['data']} - {e['ora']} | {e['commissione']}\n"
            body += e["testo"][:1200] + "\n"
            body += f"Score: {e['score']}\n"
            body += f"Match: {', '.join(e['reasons']) if e['reasons'] else 'nessuno'}\n"
            body += "\n---\n\n"

    if vuoto:
        body += "Nessun evento classificato come rilevante.\n"

    return body


# =========================
# MAIN
# =========================
def main():
    rules = load_rules(RULES_FILE)
    rules_flat = flatten_rules(rules)

    pdf_url = trova_pdf_camera()
    scarica_pdf(pdf_url, PDF_FILE)

    text = extract_text(PDF_FILE)
    text = normalize_text(text)

    eventi = parse_eventi(text)
    eventi_finali = []

    for e in eventi:
        analysis_text = f"{e['commissione']}\n{e['testo']}"
        reasons, score = match_rules(analysis_text, rules_flat)
        categoria = assegna_categoria(e, reasons)

        if categoria:
            e["reasons"] = reasons
            e["score"] = score
            e["categoria"] = categoria
            eventi_finali.append(e)

    body = build_email(pdf_url, eventi_finali)

    print("DEBUG EMAIL:")
    print("USER:", os.environ.get("EMAIL_USER"))
    print("TO:", os.environ.get("EMAIL_TO"))

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = "Monitor Camera"
    msg["From"] = os.environ["EMAIL_USER"]
    msg["To"] = os.environ["EMAIL_TO"]

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
        server.sendmail(
            os.environ["EMAIL_USER"],
            [os.environ["EMAIL_TO"]],
            msg.as_string()
        )

    print("Email inviata")


if __name__ == "__main__":
    main()