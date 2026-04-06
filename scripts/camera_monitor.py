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
PDF_FILE = "camera.pdf"


# =========================
# LOAD RULES
# =========================
def load_rules(path):
    print(f"Uso file regole: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(text):
    if not text:
        return ""
    text = text.lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_compiled_rules(rules):
    compiled = {
        "excluded_organs": [],
        "resoconto_keywords": [],
        "normative_patterns": [],
        "confitarma_keywords": [],
        "keyphrases": [],
        "norm_refs": [],
        "programs_tools": [],
        "entities": [],
    }

    # excluded_organs
    for item in rules.get("excluded_organs", []):
        if isinstance(item, str):
            compiled["excluded_organs"].append(normalize_text(item))

    # resoconto_keywords
    for item in rules.get("resoconto_keywords", []):
        if isinstance(item, str):
            compiled["resoconto_keywords"].append(normalize_text(item))

    # normative_patterns
    for item in rules.get("normative_patterns", []):
        if isinstance(item, dict):
            label = item.get("label", "")
            for p in item.get("patterns", []):
                if isinstance(p, str):
                    compiled["normative_patterns"].append({
                        "label": label,
                        "pattern": p
                    })

    # confitarma_kb
    kb = rules.get("confitarma_kb", {})

    # confitarma keywords nested
    kb_keywords = kb.get("keywords", {})
    for group_name, items in kb_keywords.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    compiled["confitarma_keywords"].append({
                        "group": group_name,
                        "value": normalize_text(item)
                    })

    # keyphrases
    for item in kb.get("keyphrases", []):
        if isinstance(item, str):
            compiled["keyphrases"].append(normalize_text(item))

    # norm refs
    norm_refs = kb.get("norm_refs", {})
    for bucket in ["italia", "ue_internazionale"]:
        for item in norm_refs.get(bucket, []):
            if isinstance(item, str):
                compiled["norm_refs"].append(normalize_text(item))

    # programs_tools
    for item in kb.get("programs_tools", []):
        if isinstance(item, str):
            compiled["programs_tools"].append(normalize_text(item))

    # entities
    for item in kb.get("entities", []):
        if isinstance(item, str):
            compiled["entities"].append(normalize_text(item))

    return compiled


# =========================
# PDF CAMERA
# =========================
def trova_pdf_camera(max_giorni=7):
    oggi = datetime.now()

    for i in range(1, max_giorni + 1):
        data = oggi - timedelta(days=i)
        data_str = data.strftime("%d%m%Y")
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


def scarica_pdf(url, output):
    r = requests.get(url, timeout=90)
    r.raise_for_status()

    with open(output, "wb") as f:
        f.write(r.content)


# =========================
# PARSING PDF
# =========================
def clean_extracted_text(text):
    text = text.replace("\x0c", "\n")
    text = text.replace(" ", " ")
    text = re.sub(r"-\s*\d+\s*-", "\n", text)
    text = re.sub(r"\n[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_eventi(text):
    righe = [r.strip() for r in text.splitlines() if r.strip()]

    pattern_data = re.compile(
        r"^(Lunedì|Martedì|Mercoledì|Giovedì|Venerdì|Sabato|Domenica)\s+\d{1,2}\s+\w+\s+\d{4}",
        re.IGNORECASE
    )
    pattern_ora = re.compile(r"^Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)", re.IGNORECASE)

    eventi = []
    data_corrente = ""
    commissione_corrente = ""
    evento_corrente = None

    for riga in righe:
        if pattern_data.match(riga):
            data_corrente = riga
            continue

        if "COMMISSIONE" in riga.upper():
            commissione_corrente = riga
            continue

        m_ora = pattern_ora.match(riga)
        if m_ora:
            if evento_corrente:
                eventi.append(evento_corrente)

            evento_corrente = {
                "data": data_corrente,
                "ora": m_ora.group(1).replace(",", "."),
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
# MATCHING RULES
# =========================
def is_excluded_organ(commissione, compiled_rules):
    text = normalize_text(commissione)
    if not text:
        return False

    for organ in compiled_rules["excluded_organs"]:
        if organ and organ in text:
            return True

    return False


def match_rules(text, compiled_rules):
    raw_text = text or ""
    normalized = normalize_text(raw_text)

    reasons = []
    score = 0

    # resoconto_keywords
    for kw in compiled_rules["resoconto_keywords"]:
        if kw and kw in normalized:
            reasons.append(f"keyword:{kw}")
            score += 3

    # normative_patterns
    for item in compiled_rules["normative_patterns"]:
        pattern = item["pattern"]
        label = item["label"] or pattern

        try:
            if re.search(pattern, normalized, re.IGNORECASE):
                reasons.append(f"normativa:{label}")
                score += 4
        except re.error:
            if normalize_text(pattern) in normalized:
                reasons.append(f"normativa:{label}")
                score += 4

    # confitarma keywords
    for item in compiled_rules["confitarma_keywords"]:
        value = item["value"]
        group = item["group"]
        if value and value in normalized:
            reasons.append(f"confitarma_keyword:{value}")
            score += 3

    # keyphrases
    for kp in compiled_rules["keyphrases"]:
        if kp and kp in normalized:
            reasons.append(f"keyphrase:{kp}")
            score += 6

    # norm refs
    for ref in compiled_rules["norm_refs"]:
        if ref and ref in normalized:
            reasons.append(f"norm_ref:{ref}")
            score += 5

    # programs_tools
    for prog in compiled_rules["programs_tools"]:
        if prog and prog in normalized:
            reasons.append(f"program:{prog}")
            score += 6

    # entities
    for ent in compiled_rules["entities"]:
        if ent and ent in normalized:
            reasons.append(f"entity:{ent}")
            score += 2

    # dedup reasons preserving order
    seen = set()
    unique_reasons = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            unique_reasons.append(r)

    return unique_reasons, score


# =========================
# CATEGORIZZAZIONE
# =========================
def assegna_categoria(evento, reasons, score):
    text = normalize_text((evento.get("commissione", "") + " " + evento.get("testo", "")))

    # 1) Trasporto marittimo
    marittimo_signals = [
        "porto", "porti", "portuale", "portualità",
        "marittimo", "marittima", "navigazione",
        "codice della navigazione", "demanio marittimo",
        "autorità di sistema portuale", "economia del mare",
        "autostrade del mare", "sea modal shift",
        "shipping", "cabotaggio", "armatore",
        "compagnie di navigazione", "gente di mare",
        "lavoro marittimo", "sanità marittima",
        "fueleu maritime", "ets marittimo", "bunkeraggio",
        "registro internazionale", "tonnage tax",
        "capitanerie", "guardia costiera"
    ]
    if any(s in text for s in marittimo_signals):
        return "INTERESSE TRASPORTO MARITTIMO"

    # 2) Industria del trasporto
    trasporto_signals = [
        "trasport", "logistica", "intermodal", "mobilità",
        "mit", "ministero delle infrastrutture e dei trasporti",
        "infrastrutture", "collegamenti", "tpl",
        "trasporto merci", "trasporto pubblico",
        "autobus", "linee marittime"
    ]
    if any(s in text for s in trasporto_signals):
        return "INTERESSE INDUSTRIA DEL TRASPORTO"

    # 3) Industria generale
    industria_generale_signals = [
        "energia", "pnrr", "decarbonizzazione", "industria",
        "mimit", "mase", "green finance", "cantieristica",
        "innovazione", "fit for 55", "eu ets", "nucleare"
    ]
    if any(s in text for s in industria_generale_signals):
        return "INTERESSE INDUSTRIALE GENERALE"

    # fallback: se ha score sufficiente ma non segnali diretti
    if score >= 6:
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
        cat = e.get("categoria")
        if cat in categorie:
            categorie[cat].append(e)

    body = "MONITOR CAMERA – ANALISI COMPLETA PDF\n\n"
    body += f"Fonte PDF: {pdf_url}\n\n"

    found_any = False

    for cat, items in categorie.items():
        if not items:
            continue

        found_any = True
        body += f"{cat}\n\n"

        for e in items:
            header = f"{e.get('data', '')} - {e.get('ora', '')} | {e.get('commissione', '')}".strip(" -|")
            body += f"{header}\n"
            body += e.get("testo", "")[:1200] + "\n"
            body += f"Score: {e.get('score', 0)}\n"
            body += f"Match: {', '.join(e.get('reasons', []))}\n"
            body += "\n---\n\n"

    if not found_any:
        body += "Nessun evento classificato.\n"

    return body


# =========================
# MAIN
# =========================
def main():
    rules = load_rules(RULES_FILE)
    compiled_rules = build_compiled_rules(rules)

    pdf_url = trova_pdf_camera()
    scarica_pdf(pdf_url, PDF_FILE)

    text = extract_text(PDF_FILE)
    text = clean_extracted_text(text)

    eventi = parse_eventi(text)
    eventi_finali = []

    for e in eventi:
        if is_excluded_organ(e.get("commissione", ""), compiled_rules):
            continue

        combined_text = f"{e.get('commissione', '')}\n{e.get('testo', '')}"
        reasons, score = match_rules(combined_text, compiled_rules)
        categoria = assegna_categoria(e, reasons, score)

        # Tieni un po' di rumore, ma serve almeno un match
        if reasons and categoria:
            e["reasons"] = reasons
            e["score"] = score
            e["categoria"] = categoria
            eventi_finali.append(e)

    body = build_email(pdf_url, eventi_finali)

    print("DEBUG EMAIL:")
    print("USER:", os.environ.get("SMTP_USER"))
    print("TO:", os.environ.get("SMTP_TO"))

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = "Monitor Camera"
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["SMTP_TO"]

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.sendmail(
            os.environ["SMTP_USER"],
            [os.environ["SMTP_TO"]],
            msg.as_string()
        )

    print("Email inviata")


if __name__ == "__main__":
    main()