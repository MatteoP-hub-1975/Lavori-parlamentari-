import os
import re
import sys
import json
import smtplib
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import fitz  # PyMuPDF
import requests


OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.today() - timedelta(days=1)).date().isoformat()


def build_bollettino_pdf_url(target_date: str) -> str:
    y, m, d = target_date.split("-")
    # pattern osservato: 2332026.pdf = 23/3/2026
    return f"https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/{int(d)}{int(m)}{y}.pdf"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def download_pdf(url: str) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=90)
    r.raise_for_status()
    return r.content


def extract_pdf_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts = []
    for page in doc:
        parts.append(page.get_text())
    return "\n".join(parts)


def find_matches(text: str):
    patterns = [
        ("Termine emendamenti", r"termine\s+per\s+la\s+presentazione[^\.:\n]{0,300}(emendament|proposte\s+emendative)"),
        ("Emendamenti", r"(emendament[oi]|proposte\s+emendative)"),
        ("Audizione", r"audizion[ei]"),
        ("DDL / PDL", r"\b(a\.c\.|c\.)\s*\d+"),
        ("Documento", r"\b(doc\.)\s*[ivxlcdm]+"),
        ("Atto del Governo", r"\batto\s+n\.\s*\d+"),
    ]

    items = []

    for tipo, pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = max(0, m.start() - 220)
            end = min(len(text), m.end() + 320)
            snippet = compact(text[start:end])

            if len(snippet) < 60:
                continue

            items.append({
                "tipo": tipo,
                "snippet": snippet,
            })

    # dedup
    seen = set()
    clean = []
    for item in items:
        key = (item["tipo"], item["snippet"])
        if key in seen:
            continue
        seen.add(key)
        clean.append(item)

    return clean


def classify_sector(snippet: str) -> str:
    s = snippet.lower()

    marittimo = [
        "marittim", "navigazion", "porto", "porti", "shipping",
        "armator", "nave", "navi", "autorità portuale", "adsp",
        "blue economy", "canale di suez", "stretto di hormuz",
    ]
    trasporto = [
        "trasport", "logistic", "ferroviar", "stradal", "autostrad",
        "aeroport", "aeronautic", "mobilità", "tpl",
        "trasporto pubblico locale", "veicoli",
    ]
    industria = [
        "energia", "industr", "imprese", "approvvigionamenti",
        "carburanti", "pnrr", "politiche di coesione",
    ]

    if any(x in s for x in marittimo):
        return "Interesse trasporto marittimo"
    if any(x in s for x in trasporto):
        return "Interesse industria del trasporto"
    if any(x in s for x in industria):
        return "Interesse industriale generale"
    return "Non attinenti"


def build_email_body(target_date: str, pdf_url: str, items):
    sections = {
        "Interesse trasporto marittimo": [],
        "Interesse industria del trasporto": [],
        "Interesse industriale generale": [],
        "Non attinenti": [],
    }

    for item in items:
        item["categoria"] = classify_sector(item["snippet"])
        sections[item["categoria"]].append(item)

    body = f"<b>Test Camera – Futuro da Bollettino Commissioni – {target_date}</b><br><br>"
    body += f'Fonte PDF: <a href="{pdf_url}">bollettino commissioni</a><br><br>'

    for sec in [
        "Interesse trasporto marittimo",
        "Interesse industria del trasporto",
        "Interesse industriale generale",
        "Non attinenti",
    ]:
        body += f"<b>=== {sec.upper()} ===</b><br><br>"
        if not sections[sec]:
            body += "Nessun elemento.<br><br>"
            continue

        for item in sections[sec]:
            body += f"<b>{item['tipo']}</b><br>"
            body += f"{item['snippet']}<br><br>"

    return body


def send_email(subject: str, body: str):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    sender = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["SMTP_TO"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)


def main():
    target_date = get_target_date()
    pdf_url = build_bollettino_pdf_url(target_date)

    print("Target date:", target_date)
    print("PDF:", pdf_url)

    pdf_bytes = download_pdf(pdf_url)
    text = extract_pdf_text(pdf_bytes)

    items = find_matches(text)

    out = {
        "target_date": target_date,
        "pdf_url": pdf_url,
        "count": len(items),
        "items": items,
    }

    out_path = OUTPUT_DIR / f"camera_future_pdf_scan_{target_date}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Trovati:", len(items))
    for item in items[:10]:
        print("-", item["tipo"], "|", item["snippet"][:220])

    subject = f"Test Camera – Futuro da Bollettino Commissioni – {target_date}"
    body = build_email_body(target_date, pdf_url, items)
    send_email(subject, body)

    print("Mail inviata.")
    print("Salvato:", out_path)


if __name__ == "__main__":
    main()