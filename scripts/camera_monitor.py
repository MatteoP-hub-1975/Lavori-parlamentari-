import requests
import re
from pdfminer.high_level import extract_text
import smtplib
from email.mime.text import MIMEText
import os
import json
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================
RULES_FILE = os.path.join(os.getcwd(), "config", "senato_monitor_rules.json")

# =========================
# LOAD RULES
# =========================
def load_rules(path):
    print(f"Uso file regole: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def compile_rules(rules):
    compiled = {}

    for cat, values in rules.items():
        compiled[cat] = [v.lower() for v in values]

    return compiled

# =========================
# TROVA PDF (logica robusta)
# =========================
def trova_pdf_camera(max_giorni=7):
    oggi = datetime.now()

    for i in range(1, max_giorni + 1):
        data = oggi - timedelta(days=i)
        data_str = data.strftime("%d%m%Y")

        url = f"https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/{data_str}.pdf"

        try:
            print(f"Tento: {url}")
            r = requests.get(url, timeout=15)

            if r.status_code == 200:
                print(f"Trovato PDF: {url}")
                return url

        except:
            pass

    raise RuntimeError("Nessun PDF trovato")

# =========================
# DOWNLOAD
# =========================
def scarica_pdf(url, output):
    r = requests.get(url)
    r.raise_for_status()

    with open(output, "wb") as f:
        f.write(r.content)

# =========================
# MATCH RULES
# =========================
def match_rules(text, compiled_rules):
    text = text.lower()
    reasons = []
    score = 0

    for category, keywords in compiled_rules.items():
        for k in keywords:
            if k in text:
                reasons.append(f"{category}:{k}")
                score += 1

    return reasons, score

# =========================
# CLASSIFICAZIONE
# =========================
def assegna_categoria(evento, reasons):
    text = (evento["testo"] + " " + evento["commissione"]).lower()

    # PRIORITÀ 1 → MARITTIMO
    if any(k in text for k in [
        "porto", "porti", "portuale",
        "marittimo", "marittima",
        "navigazione",
        "demanio marittimo",
        "autorità di sistema portuale",
        "economia del mare"
    ]):
        return "INTERESSE TRASPORTO MARITTIMO"

    # PRIORITÀ 2 → TRASPORTI
    if any(k in text for k in [
        "trasport", "logistica", "infrastrutture", "mobilità"
    ]):
        return "INTERESSE INDUSTRIA DEL TRASPORTO"

    # PRIORITÀ 3 → INDUSTRIA GENERALE
    if any(k in text for k in [
        "energia", "pnrr", "industria", "decarbonizzazione"
    ]):
        return "INTERESSE INDUSTRIALE GENERALE"

    return None  # scartiamo il resto

# =========================
# PARSING EVENTI
# =========================
def parse_eventi(text):
    righe = [r.strip() for r in text.splitlines() if r.strip()]

    pattern_data = re.compile(r"^(Lunedì|Martedì|Mercoledì|Giovedì|Venerdì|Sabato)\s+\d{1,2}")
    pattern_ora = re.compile(r"^Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)")

    eventi = []
    data_corrente = ""
    commissione_corrente = ""
    evento_corrente = None

    for riga in righe:

        if "COMMISSIONE" in riga.upper():
            commissione_corrente = riga
            continue

        if pattern_data.match(riga):
            data_corrente = riga
            continue

        m_ora = pattern_ora.match(riga)
        if m_ora:
            if evento_corrente:
                eventi.append(evento_corrente)

            evento_corrente = {
                "data": data_corrente,
                "ora": m_ora.group(1),
                "commissione": commissione_corrente,
                "testo": riga
            }
            continue

        if evento_corrente:
            evento_corrente["testo"] += "\n" + riga

    if evento_corrente:
        eventi.append(evento_corrente)

    return eventi

# =========================
# EMAIL
# =========================
def build_email(pdf_url, eventi):
    categorie = {
        "INTERESSE TRASPORTO MARITTIMO": [],
        "INTERESSE INDUSTRIA DEL TRASPORTO": [],
        "INTERESSE INDUSTRIALE GENERALE": []
    }

    for e in eventi:
        if e["categoria"]:
            categorie[e["categoria"]].append(e)

    body = "MONITOR CAMERA – ANALISI COMPLETA PDF\n\n"
    body += f"Fonte PDF: {pdf_url}\n\n"

    for cat, items in categorie.items():
        if not items:
            continue

        body += f"{cat}\n\n"

        for e in items:
            body += f"{e['data']} - {e['ora']} | {e['commissione']}\n"
            body += e["testo"][:800] + "\n"
            body += f"Score: {e['score']}\n"
            body += f"Match: {', '.join(e['reasons'])}\n"
            body += "\n---\n\n"

    return body

# =========================
# MAIN
# =========================
def main():
    rules = load_rules(RULES_FILE)
    compiled_rules = compile_rules(rules)

    pdf_url = trova_pdf_camera()
    scarica_pdf(pdf_url, "camera.pdf")

    text = extract_text("camera.pdf")

    eventi = parse_eventi(text)

    eventi_finali = []

    for e in eventi:
        reasons, score = match_rules(e["testo"], compiled_rules)
        categoria = assegna_categoria(e, reasons)

        if categoria:  # NON filtriamo troppo → solo se classificabile
            e["reasons"] = reasons
            e["score"] = score
            e["categoria"] = categoria
            eventi_finali.append(e)

    body = build_email(pdf_url, eventi_finali)

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