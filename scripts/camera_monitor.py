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

# pulizia minima
text = re.sub(r"-\s*\d+\s*-", "\n", text)          # numeri pagina tipo - 28 -
text = re.sub(r"[ \t]+\n", "\n", text)
text = re.sub(r"\n{3,}", "\n\n", text)

# taglia via l'indice iniziale: inizia dalla prima vera commissione
start_match = re.search(r"\bI COMMISSIONE PERMANENTE\b", text)
if not start_match:
    raise RuntimeError("Inizio sezioni commissioni non trovato")
text = text[start_match.start():]

# pattern intestazioni sezione
header_pattern = re.compile(
    r"^(?P<header>("
    r"[IVXLC]+\s+COMMISSIONE PERMANENTE.*"
    r"|GIUNTA PER LE AUTORIZZAZIONI.*"
    r"|COMITATO PARLAMENTARE PER.*"
    r"|COMMISSIONE PARLAMENTARE DI INCHIESTA.*"
    r"|COMMISSIONE PARLAMENTARE PER LA SEMPLIFICAZIONE.*"
    r"|COMMISSIONE PARLAMENTARE DI VIGILANZA.*"
    r"))$",
    re.MULTILINE
)

matches = list(header_pattern.finditer(text))
sections = []

for i, m in enumerate(matches):
    start = m.start()
    end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
    header = m.group("header").strip()
    content = text[start:end].strip()
    sections.append((header, content))

eventi = []

for header, content in sections:
    pezzi = re.split(r"\nOre\s+", content)
    for pezzo in pezzi[1:]:
        evento_testo = "Ore " + pezzo.strip()

        # tronca rumore finale
        evento_testo = re.split(r"\n(?:AVVISO\s+I N D I C E|I N D I C E)\b", evento_testo)[0].strip()

        m_ora = re.match(r"Ore\s+([0-9]{1,2}(?:[.,][0-9]{1,2})?)", evento_testo)
        ora = m_ora.group(1).replace(",", ".") if m_ora else ""

        eventi.append({
            "commissione": header,
            "ora": ora,
            "testo": evento_testo,
            "aggiornato": "convocazione è stata aggiornata" in evento_testo.lower(),
            "cancellato": "non avrà luogo" in evento_testo.lower(),
        })

def rilevante(e):
    txt = e["testo"].lower()
    comm = e["commissione"].lower()

    # IX Trasporti sempre rilevante
    if "ix commissione permanente" in comm or "(trasporti" in comm:
        return True

    keywords = [
        "porto", "porto di", "capitaneria", "nave", "marittim",
        "moby prince", "infrastrutture e trasporti", "logistica"
    ]
    return any(k in txt for k in keywords)

rilevanti = [e for e in eventi if rilevante(e)]

body = "MONITOR CAMERA\n\n"

if not rilevanti:
    body += "Nessun evento rilevante.\n"
else:
    for e in rilevanti:
        body += f"{e['ora']} | {e['commissione']}\n"
        body += e["testo"][:500] + "\n"
        if e["aggiornato"]:
            body += "Aggiornato\n"
        if e["cancellato"]:
            body += "Cancellato\n"
        body += "\n---\n\n"

to_email = os.environ.get("EMAIL_TO", os.environ["EMAIL_USER"])

msg = MIMEText(body, _charset="utf-8")
msg["Subject"] = "Monitor Camera"
msg["From"] = os.environ["EMAIL_USER"]
msg["To"] = to_email

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
    server.sendmail(os.environ["EMAIL_USER"], [to_email], msg.as_string())

print(f"Email inviata a: {to_email}")
print(f"Eventi rilevanti trovati: {len(rilevanti)}")