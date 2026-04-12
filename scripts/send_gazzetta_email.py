import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


EMAIL_PATH = Path("output/gazzetta_email.txt")


def send_email(subject, body):

    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    sender = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["SMTP_TO"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)


def main():
    body = EMAIL_PATH.read_text(encoding="utf-8").strip()

    subject = "Monitor Gazzetta Ufficiale"

    send_email(subject, body)

    print("Email inviata.")


if __name__ == "__main__":
    main()