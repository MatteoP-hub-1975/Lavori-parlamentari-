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


# ---------------- DATE ----------------

ITALIAN_MONTHS = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile",
    5: "maggio", 6: "giugno", 7: "luglio", 8: "agosto",
    9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre",
}


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.today() - timedelta(days=1)).date().isoformat()


def build_date_strings(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekdays = [
        "lunedì", "martedì", "mercoledì", "giovedì",
        "venerdì", "sabato", "domenica"
    ]
    return f"{weekdays[dt.weekday()]} {dt.day} {ITALIAN_MONTHS[dt.month]} {dt.year}"


# ---------------- PDF ----------------

def find_pdf(target_date):
    dt = datetime.strptime(target_date, "%Y-%m-%d").date()

    for i in range(5):
        d = dt - timedelta(days=i)
        url = f"https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/{d.day}{d.month}{d.year}.pdf"

        r = requests.get(url, headers=HEADERS)
        if r.status_code == 200:
            return url, r.content

    raise Exception("PDF non trovato")


def extract_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join([p.get_text() for p in doc])


# ---------------- PARSING ----------------

def compact(t):
    return re.sub(r"\s+", " ", t).strip()


def extract_day_section(text, target_date):
    marker = build_date_strings(target_date).lower()
    text_low = text.lower()

    start = text_low.find(marker)
    if start == -1:
        raise Exception("Data non trovata nel PDF")

    # fine = prossima data
    end_match = re.search(
        r"(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)\s+\d{1,2}\s+[a-z]+\s+2026",
        text_low[start + 20:]
    )

    end = start + end_match.start() if end_match else len(text)

    return text[start:end]


def split_commissions(text):
    parts = re.split(r"\b([IVX]+\s+COMMISSIONE.*?)\b", text)

    out = []
    for i in range(1, len(parts), 2):
        title = parts[i]
        body = parts[i + 1]
        out.append((compact(title), compact(body)))

    return out


# ---------------- EXTRACTION ----------------

def infer_type(t):
    l = t.lower()

    if "termine" in l and "emend" in l:
        return "Termine emendamenti"
    if "emend" in l:
        return "Emendamenti"
    if "audizion" in l:
        return "Audizione"
    if re.search(r"\b(c\.|a\.c\.)\s*\d+", t, re.I):
        return "DDL / PDL"
    if "atto n." in l:
        return "Atto del Governo"
    if "doc." in l:
        return "Documento"
    return None


def classify(t):
    l = t.lower()

    if any(x in l for x in ["marittim", "porto", "nave"]):
        return "Interesse trasporto marittimo"
    if "trasport" in l:
        return "Interesse industria del trasporto"
    if any(x in l for x in ["energia", "industr", "pnrr"]):
        return "Interesse industriale generale"
    return "Non attinenti"


def extract_items(section, commission):
    sentences = re.split(r"\.\s+", section)

    items = []

    for s in sentences:
        s = compact(s)

        if len(s) < 60:
            continue

        tipo = infer_type(s)
        if not tipo:
            continue

        items.append({
            "commissione": commission,
            "tipo": tipo,
            "testo": s,
            "categoria": classify(s),
        })

    return items


# ---------------- EMAIL ----------------

def build_email(date, pdf_url, items):
    sections = {
        "Interesse trasporto marittimo": [],
        "Interesse industria del trasporto": [],
        "Interesse industriale generale": [],
        "Non attinenti": [],
    }

    for i in items:
        sections[i["categoria"]].append(i)

    body = f"<b>Monitor Camera – {date}</b><br>"
    body += f'<a href="{pdf_url}">Fonte PDF</a><br><br>'

    for k in sections:
        body += f"<b>=== {k.upper()} ===</b><br><br>"

        if not sections[k]:
            body += "Nessun elemento.<br><br>"
            continue

        for i in sections[k]:
            body += f"<b>{i['tipo']}</b><br>"
            body += f"Commissione: {i['commissione']}<br>"
            body += f"{i['testo']}<br><br>"

    return body


def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["SMTP_TO"]
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


# ---------------- MAIN ----------------

def main():
    date = get_target_date()

    print("DATE:", date)

    pdf_url, pdf_bytes = find_pdf(date)
    text = extract_text(pdf_bytes)

    day_section = extract_day_section(text, date)
    commissions = split_commissions(day_section)

    all_items = []

    for name, content in commissions:
        items = extract_items(content, name)
        all_items.extend(items)

    print("ITEMS:", len(all_items))

    body = build_email(date, pdf_url, all_items)
    send_email(f"Monitor Camera – {date}", body)

    print("DONE")


if __name__ == "__main__":
    main()