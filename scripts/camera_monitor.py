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
text = re.sub(r"-\s+\d+\s+-", " ", text)   # rimuove numeri pagina tipo - 28 -
text = re.sub(r"\n{2,}", "\n\n", text)

# split per commissioni / organismi
blocchi = re.split(
    r"\n(?=(?:[IVXLC]+\s+COMMISSIONE PERMANENTE|COMMISSIONE PARLAMENTARE DI INCHIESTA|COMMISSIONE PARLAMENTARE PER|COMITATO PARLAMENTARE PER|GIUNTA PER LE AUTORIZZAZIONI))",
    text
)

eventi = []

def estrai_nome_commissione(blocco):
    righe = [r.strip() for r in blocco.splitlines() if r.strip()]
    if not righe:
        return "Commissione non identificata"
    prime = " ".join(righe[:3])
    return prime[:180]

for blocco in blocchi:
    blocco = blocco.strip()
    if not blocco:
        continue

    commissione = estrai_nome_commissione(blocco)

    pezzi = re.split(r"\nOre\s+", blocco)
    for pezzo in pezzi[1:]:
        evento_testo = "Ore " + pezzo.strip()

        # taglia quando inizia chiaramente un altro blocco
        evento_testo = re.split(
            r"\n(?=(?:[IVXLC]+\s+COMMISSIONE PERMANENTE|COMMISSIONE PARLAMENTARE DI INCHIESTA|COMMISSIONE PARLAMENTARE PER|COMITATO PARLAMENTARE PER|GIUNTA PER LE AUTORIZZAZIONI))",
            evento_testo
        )[0].strip()

        m_ora = re.match(r"Ore\s+([0-9]{1,2}(?:[.,][0-9]{2})?)", evento_testo)
        ora = m_ora.group(1).replace(",", ".") if m_ora else ""

        eventi.append({
            "commissione": commissione,
            "ora": ora,
            "testo": evento_testo,
            "aggiornato": "convocazione è stata aggiornata" in evento_testo.lower(),
            "cancellato": "non avrà luogo" in evento_testo.lower(),
        })

def rilevante(e):
    txt = e["testo"].lower()
    comm = e["commissione"].lower()

    keywords = [
        "trasport", "porto", "nave", "marittim", "logistica",
        "capitaneria", "moby prince", "infrastrutture e trasporti"
    ]

    if "trasporti" in comm:
        return True

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