import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


INDEX_URL = "https://mobile.camera.it/convocazioni-commissioni-permanenti"
BASE_URL = "https://mobile.camera.it"

HEADERS = {"User-Agent": "Mozilla/5.0"}


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def extract_commission_links(index_html: str):
    soup = BeautifulSoup(index_html, "html.parser")
    links = []

    # pagina mobile: prendiamo i link nel contenuto principale
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        text = compact(a.get_text(" ", strip=True))
        title = compact(a.get("title", ""))

        full = urljoin(BASE_URL, href)
        combined = f"{text} {title} {full}".lower()

        if "commissione" in combined and "permanenti" not in combined:
            links.append((text or title or full, full))

    # dedup
    seen = set()
    out = []
    for label, url in links:
        if url in seen:
            continue
        seen.add(url)
        out.append((label, url))
    return out


def split_blocks(text: str):
    raw = text.split("\n")
    blocks = []
    curr = []

    for line in raw:
        line = compact(line)
        if not line:
            if curr:
                blocks.append(" ".join(curr))
                curr = []
            continue
        curr.append(line)

    if curr:
        blocks.append(" ".join(curr))

    return blocks


def is_relevant_block(block: str) -> bool:
    b = block.lower()
    return any(x in b for x in [
        "audizion",
        "emendament",
        "proposte emendative",
        "termine per la presentazione",
        "doc.",
        "a.c.",
        "c.",
        "disegno di legge",
        "proposta di legge",
    ])


def infer_item_type(block: str) -> str:
    b = block.lower()

    if "termine per la presentazione" in b and ("emendament" in b or "proposte emendative" in b):
        return "Termine emendamenti"
    if "audizion" in b:
        return "Audizione"
    if "emendament" in b or "proposte emendative" in b:
        return "Emendamenti"
    if re.search(r"\b(doc\.)\s*[ivxlcdm]", block, flags=re.IGNORECASE):
        return "Documento"
    if re.search(r"\b(a\.c\.|c\.)\s*\d+", block, flags=re.IGNORECASE):
        return "DDL / PDL"
    return "Altro"


def classify_sector(block: str) -> str:
    b = block.lower()

    marittimo = [
        "marittim", "navigazion", "porto", "porti", "shipping",
        "armator", "nave", "navi", "autorità portuale", "adsp",
        "stretto di hormuz", "canale di suez", "blue economy",
    ]
    trasporto = [
        "trasport", "logistic", "ferroviar", "stradal", "autostrad",
        "aeroport", "aeronautic", "mobilità", "tpl",
    ]
    industria = [
        "energia", "industr", "imprese", "approvvigionamenti",
        "carburanti", "supply chain", "manifattur", "commercio",
    ]

    if any(x in b for x in marittimo):
        return "Interesse trasporto marittimo"
    if any(x in b for x in trasporto):
        return "Interesse industria del trasporto"
    if any(x in b for x in industria):
        return "Interesse industriale generale"
    return "Non attinenti"


def scan_commission_page(label: str, url: str):
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    blocks = split_blocks(text)

    items = []
    for block in blocks:
        if len(block) < 80:
            continue
        if not is_relevant_block(block):
            continue

        items.append({
            "commissione": label,
            "url": url,
            "tipo": infer_item_type(block),
            "categoria": classify_sector(block),
            "snippet": block,
        })

    # dedup
    seen = set()
    out = []
    for x in items:
        key = (x["commissione"], x["tipo"], x["snippet"])
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def build_email_body(items):
    sections = {
        "Interesse trasporto marittimo": [],
        "Interesse industria del trasporto": [],
        "Interesse industriale generale": [],
        "Non attinenti": [],
    }

    for item in items:
        sections[item["categoria"]].append(item)

    body = "<b>Test Camera – Futuro da convocazioni Commissioni</b><br><br>"

    order = [
        "Interesse trasporto marittimo",
        "Interesse industria del trasporto",
        "Interesse industriale generale",
        "Non attinenti",
    ]

    for sec in order:
        body += f"<b>=== {sec.upper()} ===</b><br><br>"
        if not sections[sec]:
            body += "Nessun elemento.<br><br>"
            continue

        for item in sections[sec]:
            body += f"<b>{item['tipo']}</b><br>"
            body += f"Commissione: {item['commissione']}<br>"
            body += f"{item['snippet']}<br>"
            body += f'Link: <a href="{item["url"]}">pagina commissione</a><br><br>'

    return body


def send_email(subject: str, body: str):
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
    print("Scarico indice commissioni...")
    index_html = fetch_html(INDEX_URL)
    commission_links = extract_commission_links(index_html)

    print("Commissioni trovate:", len(commission_links))

    all_items = []
    for label, url in commission_links:
        try:
            items = scan_commission_page(label, url)
            if items:
                print("-", label, "| items:", len(items))
            all_items.extend(items)
        except Exception as e:
            print("-", label, "| errore:", e)

    subject = "Test Camera – Futuro da convocazioni Commissioni"
    body = build_email_body(all_items)
    send_email(subject, body)

    print("Totale elementi trovati:", len(all_items))
    print("Mail inviata.")


if __name__ == "__main__":
    main()