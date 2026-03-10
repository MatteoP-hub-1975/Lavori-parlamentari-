import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.senato.it"
OUTPUT_DIR = Path("data/senato")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SenatoMonitor/1.0)"
}

SECTION_TITLES = {
    "ODG e Calendario",
    "DDL e relazioni",
    "Risposte scritte ad interrogazioni",
    "Resoconti",
    "Documenti",
    "Atti del Governo",
    "Emendamenti",
    "Messaggi",
}

STOP_TITLES = {
    "In questa pagina",
    "Pubblicati di recente",
    "Senato - Arcipelago",
    "Servizio - Bottom Footer",
}

TYPE_PATTERNS = [
    r"^Disegno di legge(?: \d+)?$",
    r"^O\.D\.G\. Giunte e Commissioni$",
    r"^Ordine del giorno Assemblea$",
    r"^Calendario dei lavori dell'Assemblea$",
    r"^Resoconto .+$",
    r"^Risposte scritte ad interrogazioni$",
    r"^Documento .+$",
    r"^Atto del Governo .+$",
    r"^Doc\. .+$",
]


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def is_section_title(line: str) -> bool:
    return line in SECTION_TITLES


def is_stop_title(line: str) -> bool:
    return line in STOP_TITLES


def is_type_line(line: str) -> bool:
    for pattern in TYPE_PATTERNS:
        if re.match(pattern, line, flags=re.IGNORECASE):
            return True
    return False


def parse_cli_date() -> date:
    """
    Se passi una data come argomento, usa quella.
    Esempio:
        python scripts/fetch_senato_atti.py 2026-03-09

    Altrimenti usa ieri.
    """
    if len(sys.argv) > 1:
        return datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    return date.today() - timedelta(days=1)


def build_day_url(target_date: date) -> str:
    ymd = target_date.strftime("%Y%m%d")
    return f"{BASE_URL}/leggi-e-documenti/ultimi-atti-pubblicati/periodo?from={ymd}&to={ymd}"


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def extract_main_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [compact_spaces(x) for x in text.splitlines()]
    return [x for x in lines if x]


def extract_pdf_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        label = compact_spaces(a.get_text(" ", strip=True)).lower()
        href = a["href"].strip()
        full_url = urljoin(page_url, href)

        if label == "pdf" and "/PDF/" in full_url:
            links.append(full_url)

    return links


def parse_entries_from_lines(lines: list[str], target_date: date) -> list[dict]:
    entries = []

    in_content = False
    current_section = None
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("Atti pubblicati "):
            in_content = True
            i += 1
            continue

        if not in_content:
            i += 1
            continue

        if is_stop_title(line):
            break

        if is_section_title(line):
            current_section = line
            i += 1
            continue

        if is_type_line(line):
            entry = {
                "ramo": "Senato",
                "sezione": current_section or "",
                "tipo_atto": line,
                "numero": "",
                "titolo": "",
                "data": target_date.isoformat(),
                "commissione": "",
                "seduta": "",
                "link": "",
            }

            # Caso DDL con numero già nella riga tipo: "Disegno di legge 1816"
            m_ddl = re.match(r"^Disegno di legge(?:\s+(\d+))?$", line, flags=re.IGNORECASE)
            if m_ddl and m_ddl.group(1):
                entry["numero"] = m_ddl.group(1)

            # Leggiamo le righe successive finché non troviamo:
            # - una nuova sezione
            # - un nuovo tipo atto
            # - uno stop title
            # - oppure la stringa "pdf"
            j = i + 1
            block = []

            while j < len(lines):
                candidate = lines[j]

                if is_stop_title(candidate):
                    break
                if is_section_title(candidate):
                    break
                if is_type_line(candidate):
                    break
                if candidate.lower() == "pdf":
                    break

                block.append(candidate)
                j += 1

            # Interpreta il blocco
            for item in block:
                item_clean = compact_spaces(item)

                if item_clean.startswith('"') and item_clean.endswith('"'):
                    entry["titolo"] = item_clean.strip('"')
                    continue

                if re.match(r"^\d{2}/\d{2}/\d{4}$", item_clean):
                    # Data interna dell’atto: non la usiamo come data pubblicazione.
                    continue

                if item_clean.lower().startswith("iniziativa:"):
                    continue

                if re.search(r"seduta/e?\s+n\.", item_clean, flags=re.IGNORECASE):
                    entry["seduta"] = item_clean
                    continue

                # Commissione / organo / sottotitolo
                if (
                    not entry["titolo"]
                    and not entry["commissione"]
                    and not re.match(r"^\d{2}/\d{2}/\d{4}$", item_clean)
                    and not item_clean.lower().startswith("iniziativa:")
                ):
                    # Per ODG o resoconti, la prima riga spesso è la commissione o organo
                    if entry["tipo_atto"] != "Disegno di legge" and not entry["tipo_atto"].startswith("Disegno di legge"):
                        entry["commissione"] = item_clean
                        continue

                # Se non c’è titolo quotato, la prima riga utile può fare da titolo
                if not entry["titolo"] and item_clean:
                    entry["titolo"] = item_clean

            entries.append(entry)
            i = j
            continue

        i += 1

    return entries


def attach_links(entries: list[dict], pdf_links: list[str]) -> list[dict]:
    """
    Nella pagina del Senato gli atti elencati e i relativi link PDF
    compaiono nello stesso ordine visivo.
    In questa fase 1 associamo i link per posizione.
    """
    for idx, entry in enumerate(entries):
        if idx < len(pdf_links):
            entry["link"] = pdf_links[idx]
    return entries


def normalize_entries(entries: list[dict]) -> list[dict]:
    normalized = []

    for entry in entries:
        tipo_atto = compact_spaces(entry.get("tipo_atto", ""))
        numero = compact_spaces(entry.get("numero", ""))
        titolo = compact_spaces(entry.get("titolo", ""))
        commissione = compact_spaces(entry.get("commissione", ""))
        seduta = compact_spaces(entry.get("seduta", ""))
        link = compact_spaces(entry.get("link", ""))

        # Miglioria: per i DDL il tipo standardizzato resta "DDL"
        if tipo_atto.lower().startswith("disegno di legge"):
            tipo_standard = "DDL"
        else:
            tipo_standard = tipo_atto

        normalized.append(
            {
                "ramo": "Senato",
                "sezione": compact_spaces(entry.get("sezione", "")),
                "tipo_atto": tipo_standard,
                "numero": numero,
                "titolo": titolo,
                "data": compact_spaces(entry.get("data", "")),
                "commissione": commissione,
                "seduta": seduta,
                "link": link,
            }
        )

    return normalized


def save_json(entries: list[dict], target_date: date) -> Path:
    output_path = OUTPUT_DIR / f"senato_atti_{target_date.isoformat()}.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return output_path


def main():
    target_date = parse_cli_date()
    day_url = build_day_url(target_date)

    print(f"Recupero atti Senato del giorno: {target_date.isoformat()}")
    print(f"URL: {day_url}")

    html = fetch_html(day_url)
    lines = extract_main_lines(html)
    pdf_links = extract_pdf_links(html, day_url)

    entries = parse_entries_from_lines(lines, target_date)
    entries = attach_links(entries, pdf_links)
    entries = normalize_entries(entries)

    output_path = save_json(entries, target_date)

    print(f"Atti trovati: {len(entries)}")
    print(f"File salvato in: {output_path}")


if __name__ == "__main__":
    main()
