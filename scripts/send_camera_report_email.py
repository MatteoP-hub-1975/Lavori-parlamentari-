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


def load_json_if_exists(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_analyzed_data(target_date):
    file_path = OUTPUT_DIR / f"camera_atti_analizzati_{target_date}.json"
    data = load_json_if_exists(file_path)
    return data or []


def load_agenda_operativa_data(target_date):
    file_path = OUTPUT_DIR / f"camera_agenda_operativa_{target_date}.json"
    data = load_json_if_exists(file_path)
    return data or []


def load_resoconti_data(target_date):
    file_path = OUTPUT_DIR / f"camera_resoconti_{target_date}.json"
    data = load_json_if_exists(file_path)
    return data or []


def load_odg_alerts_data(target_date):
    file_path = OUTPUT_DIR / f"camera_odg_alerts_{target_date}.json"
    data = load_json_if_exists(file_path)
    if not data:
        return []
    return data.get("items", []) or []


def build_agenda_section(items):
    blocks = []

    for item in items:
        tipo = compact_spaces(item.get("tipo_atto", ""))
        titolo = compact_spaces(item.get("titolo", ""))
        link = compact_spaces(item.get("link_pdf", ""))
        motivazione = compact_spaces(item.get("motivazione_preliminare", ""))

        lines = []
        if tipo:
            lines.append(f"<b>{tipo}</b>")
        if titolo and titolo != tipo:
            lines.append(titolo)
        if motivazione:
            lines.append(f"Motivazione: {motivazione}")
        if link:
            lines.append(f'Link: <a href="{link}">link documento</a>')

        blocks.append("<br>".join(lines) + "<br><br>")

    return blocks


def build_odg_alerts_section(items):
    blocks = []

    for item in items:
        tipo = compact_spaces(item.get("tipo", ""))
        snippet = compact_spaces(item.get("snippet", ""))

        lines = []
        if tipo:
            lines.append(f"<b>{tipo}</b>")
        if snippet:
            lines.append(snippet)

        if lines:
            blocks.append("<br>".join(lines) + "<br><br>")

    return blocks


def build_resoconti_section(items):
    blocks = []

    for item in items:
        tipo = compact_spaces(item.get("tipo_atto", ""))
        titolo = compact_spaces(item.get("titolo", ""))
        data_resoconto = compact_spaces(item.get("data_resoconto", ""))
        seduta = compact_spaces(item.get("seduta", ""))
        link = compact_spaces(item.get("link_pdf", ""))
        motivazione = compact_spaces(item.get("motivazione_preliminare", ""))

        lines = []
        if tipo:
            lines.append(f"<b>{tipo}</b>")
        if titolo:
            lines.append(titolo)
        if data_resoconto:
            lines.append(f"Data resoconto: {data_resoconto}")
        if seduta:
            lines.append(seduta)
        if motivazione:
            lines.append(f"Motivazione: {motivazione}")
        if link:
            lines.append(f'PDF: <a href="{link}">link documento</a>')

        blocks.append("<br>".join(lines) + "<br><br>")

    return blocks


def build_sections(items):
    sections = {
        "Interesse trasporto marittimo": [],
        "Interesse industria del trasporto": [],
        "Interesse industriale generale": [],
        "Non attinenti": [],
    }

    for item in items:
        categoria = item.get("categoria_finale") or item.get("categoria_preliminare") or "Non attinenti"

        tipo = compact_spaces(item.get("tipo_atto", ""))
        numero = compact_spaces(item.get("numero", ""))
        titolo = compact_spaces(item.get("titolo", ""))
        relatrice = compact_spaces(item.get("relatrice", ""))
        presentazione = compact_spaces(item.get("presentazione", ""))
        trasmissione = compact_spaces(item.get("trasmissione", ""))
        comunicazione = compact_spaces(item.get("comunicazione", ""))
        approvazione = compact_spaces(item.get("approvazione", ""))
        altri_dettagli = compact_spaces(item.get("altri_dettagli", ""))
        commissione = compact_spaces(item.get("commissione", ""))
        data_seduta = compact_spaces(item.get("data_seduta", ""))
        link = compact_spaces(item.get("link_pdf", ""))
        motivazione = compact_spaces(
            item.get("motivazione_finale") or item.get("motivazione_preliminare", "")
        )
        normative_hits = item.get("normative_hits", []) or []

        header = tipo
        if numero:
            header += f" {numero}"

        lines = [f"<b>{header}</b>"]

        if titolo:
            lines.append(titolo)
        if relatrice:
            lines.append(relatrice)
        if presentazione:
            lines.append(presentazione)
        if trasmissione:
            lines.append(trasmissione)
        if comunicazione:
            lines.append(comunicazione)
        if approvazione:
            lines.append(approvazione)
        if altri_dettagli:
            lines.append(altri_dettagli)

        if commissione:
            lines.append(f"Commissione: {commissione}")
        if data_seduta:
            lines.append(f"Data seduta: {data_seduta}")

        if categoria != "Non attinenti" and normative_hits:
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


def build_email_body(agenda_blocks, odg_alert_blocks, resoconti_blocks, sections, date):
    body = f"<b>Monitor Parlamento – Camera – {date}</b><br><br>"

    body += "<b>=== AGENDA LAVORI CAMERA ===</b><br><br>"
    if agenda_blocks:
        body += "".join(agenda_blocks)
    else:
        body += "Nessuna segnalazione.<br><br>"

    body += "<b>=== FUTURO (ODG / CONVOCAZIONI) ===</b><br><br>"
    if odg_alert_blocks:
        body += "".join(odg_alert_blocks)
    else:
        body += "Nessun elemento rilevante.<br><br>"

    body += "<b>=== RESOCONTI COMMISSIONI ===</b><br><br>"
    if resoconti_blocks:
        body += "".join(resoconti_blocks)
    else:
        body += "Nessun resoconto disponibile.<br><br>"

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
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)


def main():
    target_date = parse_target_date()

    analyzed_items = load_analyzed_data(target_date)
    agenda_items = load_agenda_operativa_data(target_date)
    odg_alert_items = load_odg_alerts_data(target_date)
    resoconti_items = load_resoconti_data(target_date)

    agenda_blocks = build_agenda_section(agenda_items)
    odg_alert_blocks = build_odg_alerts_section(odg_alert_items)
    resoconti_blocks = build_resoconti_section(resoconti_items)
    sections = build_sections(analyzed_items)

    subject = f"Monitor Parlamento – Camera – {target_date}"
    body = build_email_body(
        agenda_blocks,
        odg_alert_blocks,
        resoconti_blocks,
        sections,
        target_date,
    )

    send_email(subject, body)
    print("Email Camera inviata.")


if __name__ == "__main__":
    main()