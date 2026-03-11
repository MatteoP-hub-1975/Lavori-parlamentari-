from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import subprocess
import sys


ROME_TZ = ZoneInfo("Europe/Rome")


def get_run_mode(now_rome: datetime) -> tuple[str, str]:
    hour = now_rome.hour

    if hour < 12:
        run_mode = "morning"
        target_date = (now_rome.date() - timedelta(days=1)).isoformat()
    else:
        run_mode = "afternoon"
        target_date = now_rome.date().isoformat()

    return run_mode, target_date

def run_script(script_path: str, target_date: str) -> int:
    cmd = [sys.executable, script_path, target_date]
    print(f"Eseguo comando: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def main():
    now_rome = datetime.now(ROME_TZ)
    run_mode, target_date = get_run_mode(now_rome)

    print(f"Ora Italia: {now_rome.isoformat()}")
    print(f"Run mode: {run_mode}")
    print(f"Data target: {target_date}")

    exit_code = run_script("scripts/fetch_senato_atti.py", target_date)
    if exit_code != 0:
        raise SystemExit(exit_code)

    exit_code = run_script("scripts/ai_parse_senato_page.py", target_date)
    if exit_code != 0:
        raise SystemExit(exit_code)
        
    exit_code = run_script("scripts/analyze_senato_pdfs.py", target_date)
    if exit_code != 0:
        raise SystemExit(exit_code)
        
    exit_code = run_script("scripts/send_report_email.py", target_date)
    if exit_code != 0:
        raise SystemExit(exit_code)

    print("Monitor completato con successo.")


if __name__ == "__main__":
    main()
