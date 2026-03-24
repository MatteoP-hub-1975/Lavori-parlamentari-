import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


URL = "https://www.camera.it/leg19/76?active_tab_3806=3788&alias=76&environment=camera_internet&element_id=agenda_lavori"

OUTPUT_DIR = Path("data/camera")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/pdf,*/*",
}


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.date().isoformat()


def fetch_html(url=URL):
    r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r.text


def normalize_link(href, base_url=URL):
    href = (href or "").strip()
    if not href:
        return ""
    return urljoin