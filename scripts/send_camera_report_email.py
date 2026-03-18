import json
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path


OUTPUT_DIR = Path("data/camera")


def compact_spaces(text: str) -> str:
    return " ".join((text or "").split()).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


def load_analyzed_data(target_date):
    file_path = OUTPUT_DIR / f"camera_atti_analizzati_{target_date}.json"
    if not file_path.exists():
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_sections(items):
    sections = {
        "Interesse trasporto marittimo": [],
        "Interesse industria del trasporto": [],
        "Interesse industriale generale": [],
        "Non attinenti": [],
    }

    for item in items:
        categoria = item.get("categoria_finale") or item.get("categoria_preliminare") or "Non attinenti"

        titolo = compact_spaces(item.get("titolo", ""))
        tipo = compact_spaces(item.get("tipo_atto", ""))
        numero = compact_spaces(item.get("numero", ""))
        commissione = compact_spaces(item.get("commissione", ""))
        seduta = compact_spaces(item.get("seduta", ""))
        data_seduta = compact_spaces(item.get("data_seduta", ""))
        link = compact_spaces(item.get("link_pdf", ""))
        motivazione = compact_spaces(
            item.get("motivazione_finale") or item.get("motivazione_preliminare", "")
        )
        normative_hits = item.get("normative_hits", []) or []

        header = tipo
        if numero:
            header += f" {numero}"

        lines = [f"<b>{header}</b>", titolo]

        seduta_line = f"Commissione: {commissione} | Seduta: {seduta}"
        if data_seduta:
            seduta_line += f" | Data seduta: {data_seduta}"
        lines.append(seduta_line)

        if normative_hits:
            lines.append(f"Normative rilevanti trovate: {', '.join(normative_hits)}")

        lines.append(f"Motivazione: {motivazione}")

        if link:
            lines.append(f'PDF: <a href="{link}">link documento</a>')
        else:
            lines.append("PDF: -")

        text = "<br>".join(lines) + "<br><br>"

        if categoria in sections:
            sections[categoria].append(text)
        else:
            sections["Non attinenti"].append(text)

    return sections


def build_email_body(sections, date):
    body = f"<b>Monitor Parlamento – Camera – {date}</b><br><br>"

    body += "<b>=== INTERESSE TRASPORTO MARITTIMO ===</b><br><br>"
    if sections["Interesse trasporto marittimo"]:
        body += "".join(sections["Interesse trasporto marittimo"])
    else:
        body += "Nessun atto.<br><br>"

    body += "<b>=== INTERESSE INDUSTRIA DEL TRASPORTO ===</b><br><br>"
    if sections["Interesse industria del trasporto"]:
        body += "".join(sections["Interesse industria del trasporto"])
    else:
        body += "Nessun atto.<br><br>"

    body += "<b>=== INTERESSE INDUSTRIALE GENERALE ===</b><br><br>"
    if sections["Interesse industriale generale"]:
        body += "".join(sections["Interesse industriale generale"])
    else:
        body += "Nessun atto.<br><br>"

    body += "<b>=== NON ATTINENTI ===</b><br><br>"
    if sections["Non attinenti"]:
        body += "".join(sections["Non attinenti"])
    else:
        body += "Nessun atto.<br><br>"

    return body


def send_email(subject, body):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    sender = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["SMTP_TO"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject

    # HTML email
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)


def main():
    target_date = parse_target_date()
    items = load_analyzed_data(target_date)

    sections = build_sections(items)

    subject = f"Monitor Parlamento – Camera – {target_date}"
    body = build_email_body(sections, target_date)

    send_email(subject, body)
    print("Email Camera inviata.")


if __name__ == "__main__":
    main()