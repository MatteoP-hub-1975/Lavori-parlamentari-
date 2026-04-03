import requests
import re
from pdfminer.high_level import extract_text
import smtplib
from email.mime.text import MIMEText
import os
from datetime import datetime, timedelta

PDF_FILE = "camera.pdf"

# ---------------------------
# COSTRUZIONE URL PDF
# ---------------------------
def build_url(date_obj):
    return f"https://documenti.camera.it/_dati/leg19/lavori/Commissioni/Bollettini/{date_obj.day}{date_obj.month}{date_obj.year}.pdf"

def is_valid_pdf(response):
    return response.status_code == 200 and response.content[:4] == b"%PDF"

def download_pdf(url):
    try:
        r = requests.get(url, timeout=(15, 90))
        if is_valid_pdf(r):
            return r.content
    except requests.RequestException as e:
        print(f"Errore download {url}: {e}")
    return None

# ---------------------------
# TROVA PDF CORRETTO
# ---------------------------
def trova_pdf_camera():
    oggi = datetime.now().date()

    monday_current = oggi - timedelta(days=oggi.weekday())
    monday_previous = monday_current - timedelta(days=7)

    # giorni settimana corrente (lun → oggi)
    giorni_corrente = [
        monday_current + timedelta(days=i)
        for i in range((oggi - monday_current).days + 1)
    ]

    # settimana precedente (lun → ven)
    giorni_precedente = [
        monday_previous + timedelta(days=i)
        for i in range(5)
    ]

    candidati = giorni_corrente + giorni_precedente

    for data in candidati:
        url = build_url(data)
        print(f"Tento: {url}")
        content = download_pdf(url)
        if content:
            print(f"Trovato PDF: {url}")
            return url, content

    raise RuntimeError("Nessun PDF trovato")

# ---------------------------
# PULIZIA TESTO
# ---------------------------
def pulisci_testo(t):
    t = re.split(r"\nAVVISO", t)[0]
    t = re.split(r"I deputati possono partecipare", t)[0]
    return t.strip()

# ---------------------------
# DOWNLOAD PDF
# ---------------------------
PDF_URL, pdf_content = trova_pdf_camera()

with open(PDF_FILE, "wb") as f:
    f.write(pdf_content)

# ---------------------------
# ESTRAZIONE TESTO
# ---------------------------
text = extract_text(PDF_FILE)

text = re.sub(r"-\s*\d+\s*-", "\n", text)
text = re.sub(r"[ \t]+\n", "\n", text)
text = re.sub(r"\n{3,}", "\n\n", text)

# ---------------------------
# PARSING COMPLETO
# ---------------------------
righe = [r.strip() for r in text.splitlines() if r.strip()]

pattern_commissione = re.compile(r"^[IVXLC]+\s+COMMISSIONE\s+PERMANENTE.*")
pattern_data = re.compile(
    r"^(Lunedì|Martedì|Mercoledì|Giovedì|Venerdì|Sabato)\s+\d{1,2}\s+\w+\s+\d{4}$"
)
pattern_ora = re.compile(r"^Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)\b")

eventi = []
commissione_corrente = ""
data_corrente = ""
evento_corrente = None

for riga in righe:

    # Commissione
    if pattern_commissione.match(riga):
        commissione_corrente = riga
        continue

    # Data
    if pattern_data.match(riga):
        data_corrente = riga
        continue

    # Nuovo evento
    m_ora = pattern_ora.match(riga)
    if m_ora:
        if evento_corrente:
            evento_corrente["testo"] = pulisci_testo(evento_corrente["testo"])
            eventi.append(evento_corrente)

        evento_corrente = {
            "commissione": commissione_corrente,
            "data": data_corrente,
            "ora": m_ora.group(1).replace(",", "."),
            "testo": riga,
        }
        continue

    # Accumulo testo
    if evento_corrente:
        evento_corrente["testo"] += "\n" + riga

# ultimo evento
if evento_corrente:
    evento_corrente["testo"] = pulisci_testo(evento_corrente["testo"])
    eventi.append(evento_corrente)

# ---------------------------
# EMAIL
# ---------------------------
body = "MONITOR CAMERA – TUTTE LE COMMISSIONI\n\n"
body += f"Fonte PDF: {PDF_URL}\n\n"

if not eventi:
    body += "Nessun evento trovato.\n"
else:
    for e in eventi:
        body += f"{e['data']} - {e['ora']} | {e['commissione']}\n"
        body += e["testo"][:800] + "\n"
        body += "\n---\n\n"

to_email = os.environ.get("EMAIL_TO", os.environ["EMAIL_USER"])

msg = MIMEText(body, _charset="utf-8")
msg["Subject"] = "Monitor Camera - Tutte le Commissioni"
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
print(f"PDF usato: {PDF_URL}")
print(f"Eventi trovati: {len(eventi)}")