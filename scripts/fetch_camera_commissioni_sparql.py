import json
from datetime import datetime, timedelta
from pathlib import Path

import requests


SPARQL_ENDPOINT = "https://dati.camera.it/sparql"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_target_date():
    return (datetime.today() - timedelta(days=1)).date()


def date_from(hours_back=48):
    dt = datetime.today() - timedelta(hours=hours_back)
    return dt.date().isoformat()


def run_query(query: str) -> dict:
    headers = {"Accept": "application/sparql-results+json"}
    r = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query},
        headers=headers,
        timeout=90,
    )
    r.raise_for_status()
    return r.json()


def bindings(data: dict):
    return data.get("results", {}).get("bindings", [])


def v(row: dict, key: str) -> str:
    return row.get(key, {}).get("value", "")


def build_query(start_date: str) -> str:
    return f"""
PREFIX ocd: <http://dati.camera.it/ocd/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?dataSeduta ?organo ?titoloDiscussione ?resoconto
WHERE {{
  ?seduta a ocd:seduta ;
          dc:date ?dataSeduta ;
          ocd:rif_organo ?o .

  FILTER(?dataSeduta >= "{start_date}"^^xsd:date)

  ?o dc:title ?organo .

  FILTER(
    REGEX(LCASE(STR(?organo)), "commissione") ||
    REGEX(LCASE(STR(?organo)), "giunta")
  )

  ?discussione a ocd:discussione ;
               ocd:rif_seduta ?seduta ;
               dc:title ?titoloDiscussione .

  OPTIONAL {{
    ?seduta dc:relation ?resoconto .
    FILTER(REGEX(STR(?resoconto), "pdf", "i"))
  }}
}}
ORDER BY DESC(?dataSeduta)
LIMIT 200
""".strip()


def normalize_rows(rows):
    out = []
    seen = set()

    for row in rows:
        item = {
            "data_seduta": v(row, "dataSeduta"),
            "organo": v(row, "organo"),
            "titolo": v(row, "titoloDiscussione"),
            "link_pdf": v(row, "resoconto"),
        }

        key = (item["data_seduta"], item["organo"], item["titolo"], item["link_pdf"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def main():
    target_date = get_target_date().isoformat()
    start_date = date_from(30)

    print("SPARQL Camera - Giunte e Commissioni")
    print("Filtro da:", start_date)

    query = build_query(start_date)
    data = run_query(query)
    rows = normalize_rows(bindings(data))

    output = {
        "target_date": target_date,
        "start_date": start_date,
        "count": len(rows),
        "items": rows,
    }

    out_path = OUTPUT_DIR / f"camera_commissioni_sparql_{target_date}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Salvato:", out_path)
    print("Trovati:", len(rows))
    for item in rows[:15]:
        print("-", item["data_seduta"], "|", item["organo"], "|", item["titolo"], "|", item["link_pdf"])


if __name__ == "__main__":
    main()