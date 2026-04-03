import requests
import re
from pdfminer.high_level import extract_text
import smtplib
from email.mime.text import MIMEText
import os
from datetime import datetime, timedelta

PDF_FILE = "camera.pdf"


def build_url(date_obj):
    # La Camera usa il formato senza zeri iniziali: es. 30/3/2026 -> 3032026.pdf
    return (
        "https://documenti.camera.it/_dati/leg19/lavori/Commissioni/"
        f"Bollettini/{date_obj.day}{date_obj.month}{date_obj.year}.pdf"
    )


def is_valid_pdf_response(response):
    return response.status_code == 200 and response.content[:4] == b"%PDF"


def try_download_pdf(url, timeout=(15, 90)):
    try:
        r = requests.get(url, timeout=timeout)
        if is_valid_pdf_response(r):
            return r.content
        return None
    except requests.RequestException as e:
        print(f"Errore download {url}: {e}")
        return None


def trova_pdf_camera():
    oggi = datetime.now().date()

    # Settimana corrente: da lunedì fino a oggi
    monday_current = oggi - timedelta(days=oggi.weekday())
    giorni_settimana_corrente = [
        monday_current + timedelta(days=i)
        for i in range((oggi - monday_current).days + 1)
    ]

    # Settimana precedente: da lunedì a venerdì
    monday_previous = monday_current - timedelta(days=7)
    giorni_settimana_precedente = [
        monday_previous + timedelta(days=i)
        for i in range(5)
    ]

    # Prima cerca nella settimana corrente, poi nella precedente
    candidati = giorni_settimana_corrente + giorni_settimana_precedente

    for data in candidati:
        url = build_url(data)
        print(f"Tento: {url}")
        content = try_download_pdf(url)
        if content is not None:
            print(f"Trovato PDF: {url}")
            return url, content

    raise RuntimeError("Nessun PDF valido trovato né nella settimana corrente né nella precedente.")


def pulisci_testo(t):
    t = re.split(r"\nAVVISO", t)[0]
    t = re.split(r"I deputati possono partecipare", t)[0]
    return t.strip()


# --- trova e salva PDF ---
PDF_URL, pdf_content = trova_pdf_camera()

with open(PDF_FILE, "wb") as f:
    f.write(pdf_content)

# --- estrai testo ---
text = extract_text(PDF_FILE)

# --- pulizia base ---
text = re.sub(r"-\s*\d+\s*-", "\n", text)
text = re.sub(r"[ \t]+\n", "\n", text)
text = re.sub(r"\n{3,}", "\n\n", text)

# --- estrai sezione IX Commissione ---
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

# --- parsing riga per riga ---
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

if evento_corrente:
    evento_corrente["testo"] = pulisci_testo(evento_corrente["testo"])
    eventi.append(evento_corrente)

# --- costruisci email ---
body = "MONITOR CAMERA – IX COMMISSIONE TRASPORTI\n\n"
body += f"Fonte PDF: {PDF_URL}\n\n"

if not eventi:
    body += "Nessun evento trovato.\n"
else:
    for e in eventi:
        body += f"{e['data']} - {e['ora']} | {e['commissione']}\n"
        body += e["testo"][:800] + "\n"
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
print(f"PDF usato: {PDF_URL}")
print(f"Eventi trovati: {len(eventi)}")