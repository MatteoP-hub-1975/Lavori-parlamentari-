from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import subprocess
import sys


ROME_TZ = ZoneInfo("Europe/Rome")


def get_run_mode(now_rome: datetime) -> tuple[str, str]:
    """
    Decide quale run stiamo eseguendo in base all'ora italiana.

    Restituisce:
    - run_mode: "morning" oppure "afternoon"
    - target_date: data da passare allo script fetch_senato_atti.py in formato YYYY-MM-DD
    """
    hour = now_rome.hour

    # Regola definita insieme:
    # - run 07:00 -> prende il giorno precedente
    # - run 15:00 -> prende il giorno corrente
    #
    # Per tollerare eventuali piccoli ritardi del runner GitHub:
    # - se l'esecuzione parte prima delle 12:00 italiane => morning
    # - se parte dalle 12:00 in poi => afternoon
    if hour < 12:
        run_mode = "morning"
        target_date = (now_rome.date() - timedelta(days=1)).isoformat()
    else:
        run_mode = "afternoon"
        target_date = now_rome.date().isoformat()

    return run_mode, target_date


def run_fetch_script(target_date: str) -> int:
    """
    Esegue lo script che recupera gli atti del Senato per la data indicata.
    """
    cmd = [sys.executable, "scripts/fetch_senato_atti.py", target_date]

    print(f"Eseguo comando: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)

    return result.returncode


def main():
    now_rome = datetime.now(ROME_TZ)
    run_mode, target_date = get_run_mode(now_rome)

    print(f"Ora Italia: {now_rome.isoformat()}")
    print(f"Run mode: {run_mode}")
    print(f"Data target: {target_date}")

    exit_code = run_fetch_script(target_date)

    if exit_code != 0:
        raise SystemExit(exit_code)

    print("Monitor completato con successo.")


if __name__ == "__main__":
    main()
