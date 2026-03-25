import os
import json
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


DATA_DIR = Path("data/camera")


def load_json(path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_email(target_date):
    # ---- FILES ----
    future_path = DATA_DIR / f"camera_future_pdf_scan_{target_date}.json"
    atti_path = DATA_DIR / f"camera_atti_analizzati_{target_date}.json"
    resoconti_path = DATA_DIR / f"camera_resoconti_{target_date}.json"

    future = load_json(future_path)
    atti = load_json(atti_path)
    resoconti = load_json(resoconti_path)

    # ---- BODY ----
    body = f"<b>Monitor Parlamento – Camera – {target_date}</b><br><br>"

    # =====================
    # FUTURO (PDF)
    # =====================
    body += "<b>=== FUTURO (ODG / CONVOCAZIONI) ===</b><br><br>"

    sections = {
        "Interesse trasporto marittimo": [],
        "Interesse industria del trasporto": [],
        "Interesse industriale generale": [],
        "Non attinenti": [],
    }

    if future and "items" in future:
        for item in future["items"]:
            cat = item.get("categoria", "Non attinenti")
            sections.setdefault(cat, []).append(item)

    for sec in [
        "Interesse trasporto marittimo",
        "Interesse industria del trasporto",
        "Interesse industriale generale",
        "Non attinenti",
    ]:
        body += f"<b>=== {sec.upper()} ===</b><br><br>"

        items = sections.get(sec, [])

        if not items:
            body += "Nessun atto.<br><br>"
            continue

        for item in items:
            body += f"<b>{item.get('tipo','')}</b><br>"
            body += f"Commissione: {item.get('commissione','')}<br>"
            body += f"{item.get('testo','')}<br><br>"

    # =====================
    # RESOCONTI (passato)
    # =====================
    body += "<b>=== RESOCONTI COMMISSIONI ===</b><br><br>"

    if not resoconti:
        body += "Nessun resoconto disponibile.<br><br>"
    else:
        body += "Resoconti presenti.<br><br>"

    # =====================
    # ATTI (altri)
    # =====================
    body += "<b>=== AGENDA LAVORI CAMERA ===</b><br><br>"

    if not atti:
        body += "Nessuna segnalazione.<br><br>"
    else:
        body += "Atti presenti.<br><br>"

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


def main():
    target_date = sys.argv[1]

    body = build_email(target_date)

    send_email(
        f"Monitor Parlamento – Camera – {target_date}",
        body
    )

    print("Mail inviata.")


if __name__ == "__main__":
    main()