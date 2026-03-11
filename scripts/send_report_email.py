import json
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

OUTPUT_DIR = Path("data/senato")
EXCLUDED_ORGANS = [
    "Giunta Regolamento",
    "Giunta elezioni e immunità parlamentari",
    "Giunta provvisoria per la verifica dei poteri",
    "Commissione biblioteca e archivio storico",
    "Commissione straordinaria per il contrasto dei fenomeni di intolleranza, razzismo, antisemitismo e istigazione all'odio e alla violenza",
    "Commissione straordinaria per la tutela e la promozione dei diritti umani",
    "Commissione di inchiesta su scomparsa Orlandi e Gregori",
    "Commissione contenziosa",
    "Consiglio di garanzia",
    "Comitato per la legislazione",
]

def is_excluded_organ(item) -> bool:
    text = " ".join(
        [
            str(item.get("commissione", "")),
            str(item.get("titolo", "")),
            str(item.get("tipo_atto", "")),
        ]
    ).lower()

    return any(org.lower() in text for org in EXCLUDED_ORGANS)

def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


def load_data(target_date):
    file_path = OUTPUT_DIR / f"senato_atti_analizzati_{target_date}.json"
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

        if is_excluded_organ(item):
            continue
        categoria = item.get("categoria_finale") or item.get("categoria_preliminare")

        titolo = item.get("titolo", "")
        tipo = item.get("tipo_atto", "")
        numero = item.get("numero", "")
        commissione = item.get("commissione", "")
        seduta = item.get("seduta", "")
        link = item.get("link_pdf", "")
        motivazione = item.get("motivazione_finale") or item.get("motivazione_preliminare")

        header = tipo
        if numero:
            header += f" {numero}"

        text = f"""{header}
{titolo}
Commissione: {commissione} | Seduta: {seduta}
Motivazione: {motivazione}
PDF: {link}
"""

        if categoria in sections:
            sections[categoria].append(text)
        else:
            sections["Non attinenti"].append(text)

    return sections


def build_email_body(sections, date):

    body = f"Monitor Parlamento – Senato – {date}\n\n"

    for section, items in sections.items():

        body += f"\n=== {section.upper()} ===\n\n"

        if not items:
            body += "Nessun atto.\n\n"
            continue

        for item in items:
            body += item + "\n"

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

    items = load_data(target_date)

    sections = build_sections(items)

    subject = f"Monitor Parlamento – Senato – {target_date}"

    body = build_email_body(sections, target_date)

    send_email(subject, body)

    print("Email inviata.")


if __name__ == "__main__":
    main()
