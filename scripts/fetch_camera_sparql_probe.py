import json
from datetime import datetime, timedelta
from pathlib import Path

import requests


SPARQL_ENDPOINT = "https://dati.camera.it/sparql"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_target_date():
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()


def run_query(query):
    headers = {
        "Accept": "application/sparql-results+json"
    }

    response = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query},
        headers=headers,
        timeout=60
    )

    response.raise_for_status()
    return response.json()


def extract_bindings(data):
    return data.get("results", {}).get("bindings", [])


# =========================
# QUERY 1 → RESOCONTI
# =========================
QUERY_RESOCONTI = """
PREFIX ocd: <http://dati.camera.it/ocd/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT DISTINCT ?dataSeduta ?titoloDiscussione ?organo ?resoconto
WHERE {
  ?seduta a ocd:seduta ;
          dc:date ?dataSeduta .

  ?discussione a ocd:discussione ;
               ocd:rif_seduta ?seduta ;
               dc:title ?titoloDiscussione .

  OPTIONAL {
    ?seduta ocd:rif_organo ?o .
    ?o dc:title ?organo .
  }

  OPTIONAL {
    ?seduta dc:relation ?resoconto .
    FILTER(REGEX(STR(?resoconto), "pdf", "i"))
  }
}
ORDER BY DESC(?dataSeduta)
LIMIT 50
"""


# =========================
# QUERY 2 → AUDIZIONI
# =========================
QUERY_AUDIZIONI = """
PREFIX ocd: <http://dati.camera.it/ocd/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT DISTINCT ?dataSeduta ?organo ?titoloDiscussione ?resoconto
WHERE {
  ?seduta a ocd:seduta ;
          dc:date ?dataSeduta .

  ?discussione a ocd:discussione ;
               ocd:rif_seduta ?seduta ;
               dc:title ?titoloDiscussione .

  FILTER(REGEX(LCASE(STR(?titoloDiscussione)), "audizion"))

  OPTIONAL {
    ?seduta ocd:rif_organo ?o .
    ?o dc:title ?organo .
  }

  OPTIONAL {
    ?seduta dc:relation ?resoconto .
    FILTER(REGEX(STR(?resoconto), "pdf", "i"))
  }
}
ORDER BY DESC(?dataSeduta)
LIMIT 50
"""


# =========================
# QUERY 3 → ODG
# =========================
QUERY_ODG = """
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT DISTINCT ?titolo
WHERE {
  ?s dc:title ?titolo .
  FILTER(REGEX(LCASE(STR(?titolo)), "ordine del giorno"))
}
LIMIT 50
"""


# =========================
# QUERY 4 → EMENDAMENTI
# =========================
QUERY_EMENDAMENTI = """
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT DISTINCT ?titolo
WHERE {
  ?s dc:title ?titolo .
  FILTER(REGEX(LCASE(STR(?titolo)), "emendament"))
}
LIMIT 50
"""


def main():
    target_date = get_target_date()

    print("Eseguo SPARQL probe Camera...")

    results = {}

    # ---- RESOCONTI
    print("Query resoconti...")
    data = run_query(QUERY_RESOCONTI)
    results["resoconti"] = extract_bindings(data)

    # ---- AUDIZIONI
    print("Query audizioni...")
    data = run_query(QUERY_AUDIZIONI)
    results["audizioni"] = extract_bindings(data)

    # ---- ODG
    print("Query ODG...")
    data = run_query(QUERY_ODG)
    results["odg"] = extract_bindings(data)

    # ---- EMENDAMENTI
    print("Query emendamenti...")
    data = run_query(QUERY_EMENDAMENTI)
    results["emendamenti"] = extract_bindings(data)

    # ---- SAVE
    output_path = OUTPUT_DIR / f"camera_sparql_probe_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Salvato:", output_path)

    print("Conteggi:")
    for k, v in results.items():
        print(f"- {k}: {len(v)}")


if __name__ == "__main__":
    main()