import requests
import re
from pdfminer.high_level import extract_text
import smtplib
from email.mime.text import MIMEText
import os
from datetime import datetime, timedelta
import time

PDF_FILE = "camera.pdf"

# ---------------------------
# TROVA PDF (LOGICA CORRETTA)
# ---------------------------
def build_url(date_obj):
    return f"https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/{date_obj.day}{date_obj.month}{date_obj.year}.pdf"

def trova_pdf_camera():
    oggi = datetime.now().date()

    monday_current = oggi - timedelta(days=oggi.weekday())
    monday_previous = monday_current - timedelta(days=7)

    candidati = [monday_current, monday_previous]

    for data in candidati:
        url = build_url(data)
        print(f"Tento: {url}")

        try:
            r = requests.get(url, timeout=(15, 90))
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                print(f"Trovato PDF: {url}")
                return r.content
            else:
                print(f"Non valido: status={r.status_code}")
        except requests.RequestException as e:
            print(f"Errore: {e}")

    raise RuntimeError("Nessun PDF valido trovato")

# ---------------------------
# DOWNLOAD
# ---------------------------
pdf_content = trova_pdf_camera()

with open(PDF_FILE, "wb") as f:
    f.write(pdf_content)

# ---------------------------
# PULIZIA TESTO
# ---------------------------
def pulisci_testo(t):
    t = re.split(r"\nAVVISO", t)[0]
    t = re.split(r"I deputati possono partecipare", t)[0]
    return t.strip()

# ---------------------------
# ESTRAZIONE TESTO
# ---------------------------
text = extract_text(PDF_FILE)

text = re.sub(r"-\s*\d+\s*-", "\n", text)
text = re.sub(r"[ \t]+\n", "\n", text)
text = re.sub(r"\n{3,}", "\n\n", text)

# ---------------------------
# SEZIONE IX
# ---------------------------
match_ix = re.search(
    r"IX\s+COMMISSIONE\s+PERMANENTE.*?(?=X\s+COMMISSIONE\s+PERMANENTE)",
    text,
    re.DOTALL
)

if not match_ix:
    with open("debug_camera_text.txt", "w", encoding="utf-8") as f:
        f.write(text)
    raise RuntimeError("Sezione IX non trovata")

sezione_ix = match_ix.group(0).strip()

# ---------------------------
# PARSING
# ---------------------------
righe = [r.strip() for r in sezione_ix.splitlines() if r.strip()]

pattern_data = re.compile(
    r"^(Lunedì|Martedì|Mercoledì|Giovedì|Venerdì|Sabato)\s+\d{1,2}\s+\w+\s+\d{4}$"
)
pattern_ora = re.compile(r"^Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)\b")

eventi = []
data_corrente = ""
evento_corrente = None

for riga in righe:
    if pattern_data.match(riga):
        data_corrente = riga
        continue

    m_ora = pattern_ora.match(riga)
    if m_ora:
        if evento_corrente:
            evento_corrente["testo"] = pulisci_testo(evento_corrente["testo"])
            eventi.append(evento_corrente)

        evento_corrente = {
            "commissione": "IX COMMISSIONE PERMANENTE (TRASPORTI)",
            "data": data_corrente,
            "ora": m_ora.group(1).replace(",", "."),
            "testo": riga,
        }
        continue

    if evento_corrente:
        evento_corrente["testo"] += "\n" + riga

# ultimo evento
if evento_corrente:
    evento_corrente["testo"] = pulisci_testo(evento_corrente["testo"])
    eventi.append(evento_corrente)

# ---------------------------
# EMAIL
# ---------------------------
body = "MONITOR CAMERA – IX COMMISSIONE TRASPORTI\n\n"

if not eventi:
    body += "Nessun evento trovato.\n"
else:
    for e in eventi:
        body += f"{e['data']} - {e['ora']} | {e['commissione']}\n"
        body += e["testo"][:800] + "\n"
        body += "\n---\n\n"

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
print(f"Eventi trovati: {len(eventi)}")