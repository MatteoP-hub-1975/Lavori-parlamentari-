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


def compact_spaces(text: str) -> str:
    return " ".join((text or "").split()).strip()


def is_excluded_organ(item) -> bool:
    text = " ".join(
        [
            str(item.get("commissione", "")),
            str(item.get("titolo", "")),
            str(item.get("tipo_atto", "")),
            str(item.get("sezione", "")),
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


def format_main_item(item):
    categoria = item.get("categoria_finale") or item.get("categoria_preliminare")

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

    header = tipo
    if numero:
        header += f" {numero}"

    seduta_line = f"Commissione: {commissione} | Seduta: {seduta}"
    if data_seduta:
        seduta_line += f" | Data seduta: {data_seduta}"

    text = f"""{header}
{titolo}
{seduta_line}
Motivazione: {motivazione}
PDF: {link}
"""

    return categoria, text


def build_sections(items):
    sections = {
        "Interesse trasporto marittimo": [],
        "Interesse industria del trasporto": [],
        "Interesse industriale generale": [],
        "Non attinenti": [],
    }

    emendamenti = []
    audizioni = []
    resoconti_alert = []

    for item in items:
        if is_excluded_organ(item):
            continue

        categoria, text = format_main_item(item)

        if categoria in sections:
            sections[categoria].append(text)
        else:
            sections["Non attinenti"].append(text)

        titolo = compact_spaces(item.get("titolo", ""))
        tipo = compact_spaces(item.get("tipo_atto", ""))
        commissione = compact_spaces(item.get("commissione", ""))
        seduta = compact_spaces(item.get("seduta", ""))
        data_seduta = compact_spaces(item.get("data_seduta", ""))
        link = compact_spaces(item.get("link_pdf", ""))

        for snippet in item.get("termine_emendamenti", []) or []:
            snippet = compact_spaces(str(snippet))
            if snippet:
                emendamenti.append(
                    f"""{tipo}
{titolo}
Commissione: {commissione} | Seduta: {seduta}{f" | Data seduta: {data_seduta}" if data_seduta else ""}
Segnalazione: {snippet}
PDF: {link}
"""
                )

        for snippet in item.get("audizioni", []) or []:
            snippet = compact_spaces(str(snippet))
            if snippet:
                audizioni.append(
                    f"""{tipo}
{titolo}
Commissione: {commissione} | Seduta: {seduta}{f" | Data seduta: {data_seduta}" if data_seduta else ""}
Segnalazione: {snippet}
PDF: {link}
"""
                )

        if item.get("resoconto_alert"):
            kws = ", ".join(item.get("resoconto_keywords_found", []) or [])
            resoconti_alert.append(
                f"""{tipo}
{titolo}
Commissione: {commissione} | Seduta: {seduta}
Parole chiave trovate: {kws}
PDF: {link}
"""
            )

    return sections, emendamenti, audizioni, resoconti_alert


def build_email_body(sections, emendamenti, audizioni, resoconti_alert, date):
    body = f"Monitor Parlamento – Senato – {date}\n\n"

    body += "=== SCADENZA EMENDAMENTI ===\n\n"
    if emendamenti:
        for item in emendamenti:
            body += item + "\n"
    else:
        body += "Nessuna segnalazione.\n\n"

    body += "=== AUDIZIONI ===\n\n"
    if audizioni:
        for item in audizioni:
            body += item + "\n"
    else:
        body += "Nessuna segnalazione.\n\n"

    body += "=== RESOCONTI CON KEYWORD RILEVANTI ===\n\n"
    if resoconti_alert:
        for item in resoconti_alert:
            body += item + "\n"
    else:
        body += "Nessuna segnalazione.\n\n"

    for section, items in sections.items():
        body += f"=== {section.upper()} ===\n\n"

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

    sections, emendamenti, audizioni, resoconti_alert = build_sections(items)

    subject = f"Monitor Parlamento – Senato – {target_date}"
    body = build_email_body(
        sections,
        emendamenti,
        audizioni,
        resoconti_alert,
        target_date,
    )

    send_email(subject, body)
    print("Email inviata.")


if __name__ == "__main__":
    main()