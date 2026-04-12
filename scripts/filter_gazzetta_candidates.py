import json
import re
from pathlib import Path


RULES_PATH = Path("config/senato_monitor_rules.json")


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_rules() -> dict:
    with RULES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def collect_keywords(rules: dict) -> list[str]:
    keywords = set()

    for kw in rules.get("resoconto_keywords", []):
        if kw:
            keywords.add(kw.lower().strip())

    kb = rules.get("confitarma_kb", {})

    for values in kb.get("keywords", {}).values():
        for kw in values:
            if kw:
                keywords.add(kw.lower().strip())

    for phrase in kb.get("keyphrases", []):
        if phrase:
            keywords.add(phrase.lower().strip())

    for values in kb.get("norm_refs", {}).values():
        for kw in values:
            if kw:
                keywords.add(kw.lower().strip())

    for kw in kb.get("programs_tools", []):
        if kw:
            keywords.add(kw.lower().strip())

    for kw in kb.get("entities", []):
        if kw:
            keywords.add(kw.lower().strip())

    return sorted(keywords)


def collect_patterns(rules: dict) -> list[dict]:
    patterns = []

    for item in rules.get("normative_patterns", []):
        label = item.get("label", "")
        for pattern in item.get("patterns", []):
            if pattern:
                patterns.append({
                    "label": label,
                    "pattern": pattern
                })

    return patterns


def keyword_in_text(keyword: str, text: str) -> bool:
    keyword = keyword.strip().lower()

    # frasi composte o riferimenti con slash/trattini:
    # match come sottostringa sul testo normalizzato
    if " " in keyword or "/" in keyword or "-" in keyword:
        return keyword in text

    # parola singola o sigla:
    # match con confini di parola per evitare falsi positivi
    pattern = rf"\b{re.escape(keyword)}\b"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def score_text(text: str, keywords: list[str], patterns: list[dict]) -> dict:
    norm = normalize_text(text)

    keyword_hits = [kw for kw in keywords if keyword_in_text(kw, norm)]

    pattern_hits = []
    for item in patterns:
        try:
            if re.search(item["pattern"], norm, flags=re.IGNORECASE):
                pattern_hits.append(item["label"])
        except re.error:
            continue

    score = len(keyword_hits) + (len(pattern_hits) * 2)

    return {
        "score": score,
        "keyword_hits": keyword_hits,
        "pattern_hits": pattern_hits,
    }


def is_candidate(text: str, keywords: list[str], patterns: list[dict]) -> tuple[bool, dict]:
    result = score_text(text, keywords, patterns)
    keep = result["score"] > 0
    return keep, result


def filter_candidate_acts(atti: list[dict]) -> list[dict]:
    rules = load_rules()
    keywords = collect_keywords(rules)
    patterns = collect_patterns(rules)

    candidates = []

    for atto in atti:
        raw_text = atto.get("raw_text", "")
        keep, debug = is_candidate(raw_text, keywords, patterns)

        if keep:
            candidates.append({
                **atto,
                "prefilter_debug": debug
            })

    return candidates