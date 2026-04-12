import json
from pathlib import Path


INPUT_PATH = Path("output/gazzetta_output.json")


def build_section(title: str, data: dict) -> str:
    lines = [title]

    meta = data.get("meta", {})
    ai_output = data.get("ai_output")

    lines.append(f"Data pubblicazione: {meta.get('data_pubblicazione', '-')}")
    lines.append(f"Numero Gazzetta: {meta.get('numero_gazzetta', '-')}")
    lines.append(f"Link: {meta.get('detail_url', '-')}")
    lines.append("")

    if ai_output:
        lines.append(ai_output)
    else:
        lines.append("Nessun atto rilevante.")

    return "\n".join(lines)


def main():
    with INPUT_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    parts = []
    parts.append("MONITOR GAZZETTA UFFICIALE")
    parts.append("")

    if "serie_generale" in data:
        parts.append(build_section("=== SERIE GENERALE ===", data["serie_generale"]))
        parts.append("")

    if "unione_europea" in data:
        parts.append(build_section("=== UNIONE EUROPEA ===", data["unione_europea"]))
        parts.append("")

    email_text = "\n".join(parts).strip()
    print(email_text)


if __name__ == "__main__":
    main()