import requests
import re
from pdfminer.high_level import extract_text
import smtplib
from email.mime.text import MIMEText
import os

PDF_URL = "https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/3032026.pdf"
PDF_FILE = "camera.pdf"

r = requests.get(PDF_URL, timeout=30)
r.raise_for_status()
with open(PDF_FILE, "wb") as f:
    f.write(r.content)

text = extract_text(PDF_FILE)

text = re.sub(r"-\s*\d+\s*-", "\n", text)
text = re.sub(r"[ \t]+\n", "\n", text)
text = re.sub(r"\n{3,}", "\n\n", text)

start_marker = "IX COMMISSIONE PERMANENTE"
end_marker = "X COMMISSIONE PERMANENTE"

start = text.find(start_marker)
end = text.find(end_marker)

if start == -1 or end == -1 or end <= start:
    raise RuntimeError("Sezione IX Commissione non trovata correttamente")

sezione_ix = text[start:end].strip()

eventi_raw = re.split(r"\nOre\s+", sezione_ix)
eventi = []

for pezzo in eventi_raw[1:]:
    evento_testo = "Ore " + pezzo.strip()

    m_ora = re.match(r"Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)", evento_testo)
    ora = m_ora.group(1).replace(",", ".") if m_ora else ""

    eventi.append({
        "commissione": "IX COMMISSIONE PERMANENTE (TRASPORTI, POSTE E TELECOMUNICAZIONI)",
        "ora": ora,
        "testo": evento_testo,
        "aggiornato": "convocazione è stata aggiornata" in evento_testo.lower(),
        "cancellato": "non avrà luogo" in evento_testo.lower(),
    })

body = "MONITOR CAMERA – IX COMMISSIONE TRASPORTI\n\n"

if not eventi:
    body += "Nessun evento trovato.\n"
else:
    for e in eventi:
        body += f"{e['ora']} | {e['commissione']}\n"
        body += e["testo"][:800] + "\n"
        if e["aggiornato"]:
            body += "Aggiornato\n"
        if e["cancellato"]:
            body += "Cancellato\n"
        body += "\n---\n\n"

to_email = os.environ.get("EMAIL_TO", os.environ["EMAIL_USER"])

msg = MIMEText(body, _charset="utf-8")
msg["Subject"] = "Monitor Camera - IX Trasporti"
msg["From"] = os.environ["EMAIL_USER"]
msg["To"] = to_email

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
    server.sendmail(os.environ["EMAIL_USER"], [to_email], msg.as_string())

print(f"Email inviata a: {to_email}")
print(f"Eventi trovati nella IX Commissione: {len(eventi)}")