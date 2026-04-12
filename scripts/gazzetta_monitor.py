import json

from fetch_gazzetta_latest import get_latest_gazzette
from parse_gazzetta_detail import parse_gazzetta_detail
from filter_gazzetta_candidates import filter_candidate_acts


def main():
    latest = get_latest_gazzette()

    output = {}

    for key, meta in latest.items():
        detail_url = meta["detail_url"]
        atti = parse_gazzetta_detail(detail_url)
        candidati = filter_candidate_acts(atti)

        output[key] = {
            "meta": meta,
            "atti": atti,
            "candidati_ai": candidati,
        }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()