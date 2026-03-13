import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


ROME = ZoneInfo("Europe/Rome")


def run_script(script_path: str, target_date: str) -> int:
    cmd = [sys.executable, script_path, target_date]
    print(f"Eseguo comando: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def main():

    now_rome = datetime.now(ROME)

    print(f"Ora Italia: {now_rome.isoformat()}")

    # Analizziamo sempre il giorno precedente
    target_date = (now_rome.date() - timedelta(days=1)).isoformat()

    print(f"Data target: {target_date}")

    scripts = [
        "scripts/fetch_senato_atti.py",
        "scripts/ai_parse_senato_page.py",
        "scripts/analyze_senato_pdfs.py",
        "scripts/send_report_email.py",
    ]

    for script in scripts:
        code = run_script(script, target_date)
        if code != 0:
            raise RuntimeError(f"Errore nello script {script}")


if __name__ == "__main__":
    main()