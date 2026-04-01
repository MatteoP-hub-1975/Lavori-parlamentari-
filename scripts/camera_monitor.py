import requests
import re
from pdfminer.high_level import extract_text
import smtplib
from email.mime.text import MIMEText
import os

PDF_URL = "https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/3032026.pdf"
PDF_FILE = "camera.pdf"

# --- scarica PDF ---
r = requests.get(PDF_URL, timeout=30)
r.raise_for_status()
with open(PDF_FILE, "wb") as f:
    f.write(r.content)

# --- estrai testo ---
text = extract_text(PDF_FILE)

# --- split per commissioni ---
blocchi = re.split(r"\n(?=[IVXLC]+\s+COMMISSIONE PERMANENTE)", text)

eventi = []
for blocco in blocchi:
    parts = re.split(r"\nOre\s", blocco)
    for p in parts[1:]:
        eventi.append(p.strip())

def parse_evento(e):
    return {
        "commissione": e.split("\n")[0][:80],
        "ora": e[:5],
        "testo": e,
        "aggiornato": "aggiornata" in e.lower(),
        "cancellato": "non avrà luogo" in e.lower()
    }

parsed = [parse_evento(e) for e in eventi]

def rilevante(e):
    txt = e["testo"].lower()
    return any(k in txt for k in [
        "trasport", "porto", "nave", "marittim", "logistica"
    ])

rilevanti = [e for e in parsed if rilevante(e)]

# --- costruisci email ---
body = "MONITOR CAMERA\n\n"

if not rilevanti:
    body += "Nessun evento rilevante.\n"
else:
    for e in rilevanti:
        body += f"{e['ora']} | {e['commissione']}\n"
        body += e["testo"][:400] + "\n"
        if e["aggiornato"]:
            body += "Aggiornato\n"
        if e["cancellato"]:
            body += "Cancellato\n"
        body += "\n---\n\n"

# --- invio email ---
to_email = os.environ.get("EMAIL_TO", os.environ["EMAIL_USER"])

msg = MIMEText(body, _charset="utf-8")
msg["Subject"] = "Monitor Camera"
msg["From"] = os.environ["EMAIL_USER"]
msg["To"] = to_email

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
    server.sendmail(
        os.environ["EMAIL_USER"],
        [to_email],
        msg.as_string()
    )

print(f"Email inviata a: {to_email}")