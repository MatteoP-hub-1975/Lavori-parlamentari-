import os
import re
import sys
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import fitz
import requests


HEADERS = {"User-Agent": "Mozilla/5.0"}


# ---------------- DATE ----------------

def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.today() - timedelta(days=1)).date().isoformat()


# ---------------- PDF ----------------

def find_pdf(date):
    dt = datetime.strptime(date, "%Y-%m-%d").date()

    for i in range(7):
        d = dt - timedelta(days=i)
        url = f"https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/{d.day}{d.month}{d.year}.pdf"
        r = requests.get(url, headers=HEADERS, timeout=60)
        if r.status_code == 200:
            return url, r.content

    raise Exception("PDF non trovato")


def extract_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join(p.get_text() for p in doc)


# ---------------- CLEAN ----------------

def compact(t):
    return re.sub(r"\s+", " ", t).strip()


def normalize_lines(text):
    lines = []
    for l in text.split("\n"):
        l = compact(l)
        if not l:
            continue
        if re.fullmatch(r"-?\s*\d+\s*-?", l):
            continue
        if "indice convocazioni" in l.lower():
            continue
        lines.append(l)
    return lines


# ---------------- COMMISSIONI ----------------

def is_commission(line):
    return bool(re.match(r"^[IVX]+\s+[A-Z]", line))


def split_commissions(text):
    lines = normalize_lines(text)

    sections = []
    current = None
    buffer = []

    for line in lines:
        if is_commission(line):
            if current:
                sections.append((current, " ".join(buffer)))
            current = line
            buffer = []
        else:
            if current:
                buffer.append(line)

    if current:
        sections.append((current, " ".join(buffer)))

    return sections


# ---------------- CLASSIFICAZIONE ----------------

def is_relevant(text):
    t = text.lower()

    maritime = [
        "marittim", "porto", "porti", "nave", "navi",
        "shipping", "armator", "cabotaggio", "adsp"
    ]

    transport = [
        "trasport", "logistica", "mobilità",
        "tpl", "autotrasporto", "ferrovia"
    ]

    industry = [
        "energia", "pnrr", "industria",
        "carburanti", "approvvigionamenti"
    ]

    if any(k in t for k in maritime):
        return "marittimo"

    if any(k in t for k in transport):
        return "trasporti"

    if any(k in t for k in industry):
        return "industria"

    return None


def detect_type(t):
    l = t.lower()

    if "emendament" in l:
        return "Emendamenti"
    if "termine per la presentazione" in l:
        return "Termine emendamenti"
    if "audizion" in l:
        return "Audizione"
    if re.search(r"\b(c\.|a\.c\.)\s*\d+", t, re.I):
        return "DDL / PDL"
    if "atto n." in l:
        return "Atto del Governo"

    return "Altro"


# ---------------- ESTRAZIONE ----------------

def extract_items(section, commission):
    sentences = re.split(r"\.\s+", section)

    items = []

    for s in sentences:
        s = compact(s)

        if len(s) < 80:
            continue

        category = is_relevant(s)
        if not category:
            continue

        items.append({
            "commissione": commission,
            "tipo": detect_type(s),
            "testo": s,
            "categoria": category
        })

    return items


# ---------------- EMAIL ----------------

def build_email(date, pdf_url, items):
    sections = {
        "marittimo": [],
        "trasporti": [],
        "industria": []
    }

    for i in items:
        sections[i["categoria"]].append(i)

    body = f"<b>Monitor Camera – {date}</b><br>"
    body += f'<a href="{pdf_url}">Fonte PDF</a><br><br>'

    labels = {
        "marittimo": "INTERESSE TRASPORTO MARITTIMO",
        "trasporti": "INTERESSE INDUSTRIA DEL TRASPORTO",
        "industria": "INTERESSE INDUSTRIALE GENERALE"
    }

    for k in sections:
        body += f"<b>=== {labels[k]} ===</b><br><br>"

        if not sections[k]:
            body += "Nessun elemento.<br><br>"
            continue

        for i in sections[k]:
            body += f"<b>{i['tipo']}</b><br>"
            body += f"Commissione: {i['commissione']}<br>"
            body += f"{i['testo']}<br><br>"

    return body


def send_email(subject, body):
    if not all(k in os.environ for k in ["SMTP_USER", "SMTP_PASSWORD", "SMTP_TO"]):
        print("SMTP non configurato")
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


# ---------------- MAIN ----------------

def main():
    date = get_target_date()

    print("DATE:", date)

    pdf_url, pdf_bytes = find_pdf(date)
    text = extract_text(pdf_bytes)

    commissions = split_commissions(text)

    print("COMMISSIONS:", len(commissions))

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