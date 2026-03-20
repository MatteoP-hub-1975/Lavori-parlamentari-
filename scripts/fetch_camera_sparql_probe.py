import json
from datetime import datetime, timedelta
from pathlib import Path

import requests


SPARQL_ENDPOINT = "https://dati.camera.it/sparql"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_target_date():
    return (datetime.today() - timedelta(days=1)).date()


def get_date_filter(days=5):
    today = datetime.today().date()
    start = today - timedelta(days=days)
    return start.isoformat()


def run_query(query):
    headers = {"Accept": "application/sparql-results+json"}

    r = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query},
        headers=headers,
        timeout=60
    )
    r.raise_for_status()
    return r.json()


def extract(data):
    return data.get("results", {}).get("bindings", [])


def val(x, key):
    return x.get(key, {}).get("value", "")


# =========================
# QUERY RESOCONTI (FILTRATI)
# =========================
def build_query_resoconti(date_from):
    return f"""
    PREFIX ocd: <http://dati.camera.it/ocd/>
    PREFIX dc: <http://purl.org/dc/elements/1.1/>

    SELECT DISTINCT ?dataSeduta ?titolo ?organo ?resoconto
    WHERE {{
      ?seduta a ocd:seduta ;
              dc:date ?dataSeduta .

      FILTER(?dataSeduta >= "{date_from}"^^xsd:date)

      ?discussione a ocd:discussione ;
                   ocd:rif_seduta ?seduta ;
                   dc:title ?titolo .

      OPTIONAL {{
        ?seduta ocd:rif_organo ?o .
        ?o dc:title ?organo .
      }}

      OPTIONAL {{
        ?seduta dc:relation ?resoconto .
        FILTER(REGEX(STR(?resoconto), "pdf", "i"))
      }}
    }}
    ORDER BY DESC(?dataSeduta)
    LIMIT 50
    """


# =========================
# QUERY AUDIZIONI (FILTRATE)
# =========================
def build_query_audizioni(date_from):
    return f"""
    PREFIX ocd: <http://dati.camera.it/ocd/>
    PREFIX dc: <http://purl.org/dc/elements/1.1/>

    SELECT DISTINCT ?dataSeduta ?titolo ?organo ?resoconto
    WHERE {{
      ?seduta a ocd:seduta ;
              dc:date ?dataSeduta .

      FILTER(?dataSeduta >= "{date_from}"^^xsd:date)

      ?discussione a ocd:discussione ;
                   ocd:rif_seduta ?seduta ;
                   dc:title ?titolo .

      FILTER(REGEX(LCASE(STR(?titolo)), "audizion"))

      OPTIONAL {{
        ?seduta ocd:rif_organo ?o .
        ?o dc:title ?organo .
      }}

      OPTIONAL {{
        ?seduta dc:relation ?resoconto .
        FILTER(REGEX(STR(?resoconto), "pdf", "i"))
      }}
    }}
    ORDER BY DESC(?dataSeduta)
    LIMIT 50
    """


def main():
    target_date = get_target_date()
    date_from = get_date_filter(5)

    print("SPARQL Camera V2...")
    print("Filtro da:", date_from)

    # ---- RESOCONTI
    print("Query resoconti...")
    q1 = build_query_resoconti(date_from)
    resoconti_raw = extract(run_query(q1))

    resoconti = []
    for r in resoconti_raw:
        resoconti.append({
            "data": val(r, "dataSeduta"),
            "titolo": val(r, "titolo"),
            "organo": val(r, "organo"),
            "pdf": val(r, "resoconto"),
        })

    # ---- AUDIZIONI
    print("Query audizioni...")
    q2 = build_query_audizioni(date_from)
    audizioni_raw = extract(run_query(q2))

    audizioni = []
    for r in audizioni_raw:
        audizioni.append({
            "data": val(r, "dataSeduta"),
            "titolo": val(r, "titolo"),
            "organo": val(r, "organo"),
            "pdf": val(r, "resoconto"),
        })

    results = {
        "resoconti": resoconti,
        "audizioni": audizioni
    }

    output_path = OUTPUT_DIR / f"camera_sparql_v2_{target_date}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Salvato:", output_path)
    print("Conteggi:")
    print("- resoconti:", len(resoconti))
    print("- audizioni:", len(audizioni))


if __name__ == "__main__":
    main()