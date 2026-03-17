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

        lines = [header, titolo]

        seduta_line = f"Commissione: {commissione} | Seduta: {seduta}"
        if data_seduta:
            seduta_line += f" | Data seduta: {data_seduta}"
        lines.append(seduta_line)

        if normative_hits:
            lines.append(f"Normative rilevanti trovate: {', '.join(normative_hits)}")

        lines.append(f"Motivazione: {motivazione}")
        lines.append(f"PDF: {link}")

        text = "\n".join(lines) + "\n"

        if categoria in sections:
            sections[categoria].append(text)
        else:
            sections["Non attinenti"].append(text)

    return sections


def build_email_body(sections, date):
    body = f"Monitor Parlamento – Camera – {date}\n\n"

    body += "=== INTERESSE TRASPORTO MARITTIMO ===\n\n"
    if sections["Interesse trasporto marittimo"]:
        for item in sections["Interesse trasporto marittimo"]:
            body += item + "\n"
    else:
        body += "Nessun atto.\n\n"

    body += "=== INTERESSE INDUSTRIA DEL TRASPORTO ===\n\n"
    if sections["Interesse industria del trasporto"]:
        for item in sections["Interesse industria del trasporto"]:
            body += item + "\n"
    else:
        body += "Nessun atto.\n\n"

    body += "=== INTERESSE INDUSTRIALE GENERALE ===\n\n"
    if sections["Interesse industriale generale"]:
        for item in sections["Interesse industriale generale"]:
            body += item + "\n"
    else:
        body += "Nessun atto.\n\n"

    body += "=== NON ATTINENTI ===\n\n"
    if sections["Non attinenti"]:
        for item in sections["Non attinenti"]:
            body += item + "\n"
    else:
        body += "Nessun atto.\n\n"

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
    msg.attach(MIMEText(body, "plain"))

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