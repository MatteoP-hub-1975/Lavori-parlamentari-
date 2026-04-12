import json

from fetch_gazzetta_latest import get_latest_gazzette
from parse_gazzetta_detail import parse_gazzetta_detail
from filter_gazzetta_candidates import filter_candidate_acts
from analyze_gazzetta_ai import analyze_atti


def main():
    latest = get_latest_gazzette()
    output = {}

    for key, meta in latest.items():
        detail_url = meta["detail_url"]
        atti = parse_gazzetta_detail(detail_url)
        candidati = filter_candidate_acts(atti)

        ai_output = None
        if candidati:
            ai_input = [{"raw_text": item.get("raw_text", "")} for item in candidati]
            ai_output = analyze_atti(ai_input)

        output[key] = {
            "meta": meta,
            "atti": atti,
            "candidati_ai": candidati,
            "ai_output": ai_output,
        }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()