import os
import re
import sys
import json
import smtplib
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import fitz
import requests


OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}

ITALIAN_MONTHS = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile",
    5: "maggio", 6: "giugno", 7: "luglio", 8: "agosto",
    9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre",
}

WEEKDAYS = [
    "lunedì", "martedì", "mercoledì", "giovedì",
    "venerdì", "sabato", "domenica"
]


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.today() - timedelta(days=1)).date().isoformat()


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def build_date_strings(date_str: str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    full = f"{WEEKDAYS[dt.weekday()]} {dt.day} {ITALIAN_MONTHS[dt.month]} {dt.year}"
    short = f"{dt.day} {ITALIAN_MONTHS[dt.month]} {dt.year}"
    return full.lower(), short.lower()


def find_pdf(target_date: str):
    dt = datetime.strptime(target_date, "%Y-%m-%d").date()

    for i in range(7):
        d = dt - timedelta(days=i)
        url = f"https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/{d.day}{d.month}{d.year}.pdf"
        r = requests.get(url, headers=HEADERS, timeout=90)
        if r.status_code == 200 and "pdf" in (r.headers.get("Content-Type", "").lower()):
            return url, r.content

    raise Exception("PDF non trovato")


def extract_pages(pdf_bytes: bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages.append({"page_num": i + 1, "text": text})
    return pages


def is_index_page(text: str) -> bool:
    t = text.lower()
    return (
        "i n d i c e c o n v o c a z i o n i" in t
        or "indice convocazioni alla data" in t
    )


def extract_day_pages(pages, target_date: str):
    """
    Cerca l'ULTIMA pagina che contiene la data target:
    in genere è l'inizio della sezione vera, non l'indice.
    """
    full_marker, short_marker = build_date_strings(target_date)

    candidate_indexes = []
    for idx, page in enumerate(pages):
        low = page["text"].lower()
        if full_marker in low or short_marker in low:
            candidate_indexes.append(idx)

    if not candidate_indexes:
        raise Exception("Data target non trovata nel PDF")

    start_idx = candidate_indexes[-1]

    out = []
    next_day_pattern = re.compile(
        r"\b(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)\s+\d{1,2}\s+"
        r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4}",
        re.IGNORECASE
    )

    started = False

    for idx in range(start_idx, len(pages)):
        text = pages[idx]["text"]

        if is_index_page(text):
            continue

        if not started:
            out.append(text)
            started = True
            continue

        # se trovi una nuova data esplicita di altro giorno, stop
        m = next_day_pattern.search(text)
        if m:
            found = compact(m.group(0)).lower()
            if target_date not in found:
                break

        out.append(text)

    return "\n".join(out)


def normalize_lines(text: str):
    lines = []
    for raw in text.replace("\r", "\n").split("\n"):
        line = compact(raw)
        if not line:
            continue
        if re.fullmatch(r"-?\s*\d+\s*-?", line):
            continue
        if "i n d i c e c o n v o c a z i o n i" in line.lower():
            continue
        if "indice convocazioni alla data" in line.lower():
            continue
        lines.append(line)
    return lines


def is_commission_heading(line: str) -> bool:
    line = compact(line)

    patterns = [
        r"^[IVX]+\s+[A-ZÀ-Ú].+",
        r"^COMMISSIONI RIUNITE\b",
        r"^COMMISSIONE PARLAMENTARE\b",
        r"^COMMISSIONE PLENARIA\b",
        r"^COMITATO\b",
    ]

    return any(re.match(p, line, flags=re.IGNORECASE) for p in patterns)


def clean_commission_name(line: str) -> str:
    line = compact(line)
    line = re.sub(r"\s+\.\s+\.\s+\.\s+.*$", "", line)
    return line


def split_commissions(day_text: str):
    lines = normalize_lines(day_text)

    sections = []
    current_commission = None
    current_lines = []

    for line in lines:
        if is_commission_heading(line):
            if current_commission and current_lines:
                sections.append((current_commission, "\n".join(current_lines)))
            current_commission = clean_commission_name(line)
            current_lines = []
            continue

        if current_commission:
            current_lines.append(line)

    if current_commission and current_lines:
        sections.append((current_commission, "\n".join(current_lines)))

    return sections


def infer_type(text: str):
    low = text.lower()

    if "termine per la presentazione" in low and ("emend" in low or "proposte emendative" in low):
        return "Termine emendamenti"
    if "esame emendamenti" in low or "proposte emendative" in low or "emendament" in low:
        return "Emendamenti"
    if "audizion" in low:
        return "Audizione"
    if re.search(r"\b(a\.c\.|c\.)\s*\d+", text, re.I):
        return "DDL / PDL"
    if re.search(r"\bdoc\.\s*[ivxlcdm]+", text, re.I):
        return "Documento"
    if re.search(r"\batto\s+n\.\s*\d+", text, re.I):
        return "Atto del Governo"
    return None


def classify(text: str):
    low = text.lower()

    if any(x in low for x in ["marittim", "porto", "porti", "nave", "navi", "navigazion", "armator", "shipping", "adsp", "cabotaggio"]):
        return "Interesse trasporto marittimo"
    if any(x in low for x in ["trasport", "trasporto pubblico locale", "tpl", "mobilità", "logistic", "veicoli", "ferroviar", "aeroport", "autostrad", "autobus"]):
        return "Interesse industria del trasporto"
    if any(x in low for x in ["energia", "industr", "imprese", "pnrr", "politiche di coesione", "approvvigionamenti", "carburanti"]):
        return "Interesse industriale generale"
    return "Non attinenti"


def extract_items(section_text: str, commissione: str, data_seduta: str):
    """
    Cerca pattern rilevanti all'interno della singola commissione
    e salva snippet con contesto, senza uscire dalla commissione stessa.
    """
    patterns = [
        ("Termine emendamenti", r"termine\s+per\s+la\s+presentazione[^\.:\n]{0,400}(?:emendament|proposte\s+emendative)"),
        ("Emendamenti", r"(?:esame\s+emendamenti[^\.:\n]{0,280}|proposte\s+emendative[^\.:\n]{0,280}|ed\s+emendamenti[^\.:\n]{0,280})"),
        ("Audizione", r"(?:AUDIZIONI(?:\s+INFORMALI)?[^\.:\n]{0,280}|audizion[ei][^\.:\n]{0,320})"),
        ("DDL / PDL", r"(?:A\.C\.|C\.)\s*\d+[^\n\.]{0,250}"),
        ("Documento", r"(?:Doc\.)\s*[IVXLCDM]+(?:,\s*n\.\s*\d+)?[^\n\.]{0,250}"),
        ("Atto del Governo", r"Atto\s+n\.\s*\d+[^\n\.]{0,250}"),
    ]

    items = []

    for tipo, pattern in patterns:
        for m in re.finditer(pattern, section_text, flags=re.IGNORECASE):
            start = max(0, m.start() - 120)
            end = min(len(section_text), m.end() + 180)
            snippet = compact(section_text[start:end])

            if len(snippet) < 35:
                continue

            if "i n d i c e c o n v o c a z i o n i" in snippet.lower():
                continue
            if "indice convocazioni alla data" in snippet.lower():
                continue

            items.append({
                "data_seduta": data_seduta,
                "commissione": commissione,
                "tipo": tipo,
                "testo": snippet,
                "categoria": classify(snippet),
            })

    seen = set()
    clean = []
    for item in items:
        key = (item["commissione"], item["tipo"], item["testo"])
        if key in seen:
            continue
        seen.add(key)
        clean.append(item)

    return clean


def build_email(date: str, pdf_url: str, items):
    sections = {
        "Interesse trasporto marittimo": [],
        "Interesse industria del trasporto": [],
        "Interesse industriale generale": [],
        "Non attinenti": [],
    }

    for item in items:
        sections[item["categoria"]].append(item)

    body = f"<b>Monitor Camera – {date}</b><br>"
    body += f'Fonte PDF: <a href="{pdf_url}">link documento</a><br><br>'

    for section_name in [
        "Interesse trasporto marittimo",
        "Interesse industria del trasporto",
        "Interesse industriale generale",
        "Non attinenti",
    ]:
        body += f"<b>=== {section_name.upper()} ===</b><br><br>"

        if not sections[section_name]:
            body += "Nessun elemento.<br><br>"
            continue

        for item in sections[section_name]:
            body += f"<b>{item['tipo']}</b><br>"
            body += f"Data seduta: {item['data_seduta']}<br>"
            body += f"Commissione: {item['commissione']}<br>"
            body += f"{item['testo']}<br><br>"

    return body


def save_json(date: str, pdf_url: str, items):
    out_path = OUTPUT_DIR / f"camera_future_pdf_scan_{date}.json"
    payload = {
        "target_date": date,
        "pdf_url": pdf_url,
        "count": len(items),
        "items": items,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def send_email(subject: str, body: str):
    if not all(k in os.environ for k in ["SMTP_USER", "SMTP_PASSWORD", "SMTP_TO"]):
        return

    msg = MIMEMultipart()
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["SMTP_TO"]
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


def main():
    date = get_target_date()
    print("DATE:", date)

    pdf_url, pdf_bytes = find_pdf(date)
    print("PDF:", pdf_url)

    pages = extract_pages(pdf_bytes)
    day_text = extract_day_pages(pages, date)
    commissions = split_commissions(day_text)

    print("COMMISSIONS:", len(commissions))

    all_items = []
    for commissione, content in commissions:
        items = extract_items(content, commissione, date)
        all_items.extend(items)

    print("ITEMS:", len(all_items))
    for item in all_items[:10]:
        print("-", item["tipo"], "|", item["commissione"], "|", item["testo"][:220])

    out_path = save_json(date, pdf_url, all_items)
    body = build_email(date, pdf_url, all_items)
    send_email(f"Monitor Camera – {date}", body)

    print("JSON:", out_path)
    print("DONE")


if __name__ == "__main__":
    main()