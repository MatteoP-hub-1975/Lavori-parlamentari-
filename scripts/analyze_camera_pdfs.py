import json
import os
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup
from openai import OpenAI


OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RULES_PATH = Path("config/senato_monitor_rules.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/pdf,application/octet-stream,text/html,*/*",
}


def load_rules():
    with RULES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


RULES = load_rules()
RESOCONTO_KEYWORDS = [x.lower() for x in RULES["resoconto_keywords"]]
NORMATIVE_PATTERNS = RULES["normative_patterns"]
CONFITARMA_KB = RULES.get("confitarma_kb", {})


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_target_date():
    if len(sys.argv) < 2:
        raise ValueError("Devi passare una data YYYY-MM-DD")
    return sys.argv[1]


def is_odg(item) -> bool:
    text = " ".join(
        [
            str(item.get("tipo_atto", "")),
            str(item.get("titolo", "")),
            str(item.get("sezione", "")),
        ]
    ).lower()
    return "o.d.g" in text or "odg" in text or "ordine del giorno" in text


def is_resoconto(item) -> bool:
    text = " ".join(
        [
            str(item.get("tipo_atto", "")),
            str(item.get("titolo", "")),
            str(item.get("sezione", "")),
        ]
    ).lower()
    return "resoconto" in text


def normalize_camera_pdf_candidate(url: str) -> str:
    url = (url or "").strip()

    if not url:
        return ""

    lowered = url