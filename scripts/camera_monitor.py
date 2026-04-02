import requests
import re
from pdfminer.high_level import extract_text
import smtplib
from email.mime.text import MIMEText
import os

PDF_URL = "https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/3032026.pdf"
PDF_FILE = "camera.pdf"

def pulisci_testo(t):
    t = re.split(r"\nAVVISO", t)[0]
    t = re.split(r"I deputati possono partecipare", t)[0]
    return t.strip()

# --- scarica PDF ---
r = requests.get(PDF_URL, timeout=30)
r.raise_for_status()
with open(PDF_FILE, "wb") as f:
    f.write(r.content)

# --- estrai testo ---
text = extract_text(PDF_FILE)

# --- pulizia base ---
text = re.sub(r"-\s*\d+\s*-", "\n", text)
text = re.sub(r"[ \t]+\n", "\n", text)
text = re.sub(r"\n{3,}", "\n\n", text)

# --- estrai sezione IX Commissione (robusto) ---
match_ix = re.search(
    r"IX\s+COMMISSIONE\s+PERMANENTE.*?(?=X\s+COMMISSIONE\s+PERMANENTE)",
    text,
    re.DOTALL
)

if not match_ix:
    with open("debug_camera_text.txt", "w", encoding="utf-8") as f:
        f.write(text)
    raise RuntimeError("Sezione IX Commissione non trovata. Vedi debug_camera_text.txt")

sezione_ix = match_ix.group(0).strip()

# --- estrai eventi ---
eventi_raw = re.split(r"\nOre\s+", sezione_ix)
eventi = []

for pezzo in eventi_raw[1:]:
    evento_testo = "Ore " + pezzo.strip()
    evento_testo = pulisci_testo(evento_testo)

    m_ora = re.match(r"Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)", evento_testo)
    ora = m_ora.group(1).replace(",", ".") if m_ora else ""

    eventi.append({
        "commissione": "IX COMMISSIONE PERMANENTE (TRASPORTI, POSTE E TELECOMUNICAZIONI)",
        "ora": ora,
        "testo": evento_testo,
        "aggiornato": "convocazione è stata aggiornata" in evento_testo.lower(),
        "cancellato": "non avrà luogo" in evento_testo.lower(),
    })

# --- costruisci email ---
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

# --- invio email ---
to_email = os.environ.get("EMAIL_TO", os.environ["EMAIL_USER"])

msg = MIMEText(body, _charset="utf-8")
msg["Subject"] = "Monitor Camera - IX Trasporti"
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
print(f"Eventi trovati nella IX Commissione: {len(eventi)}")