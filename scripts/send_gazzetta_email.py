import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


EMAIL_PATH = Path("output/gazzetta_email.txt")


def main():
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    email_from = os.environ["EMAIL_FROM"]
    email_to = os.environ["EMAIL_TO"]

    body = EMAIL_PATH.read_text(encoding="utf-8").strip()

    msg = EmailMessage()
    msg["Subject"] = "Monitor Gazzetta Ufficiale"
    msg["From"] = email_from
    msg["To"] = email_to
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)

    print("Email inviata.")


if __name__ == "__main__":
    main()