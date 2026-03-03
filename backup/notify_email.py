import os
import smtplib
from email.mime.text import MIMEText


def send(subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    sender = os.getenv("SMTP_FROM", user)
    to_addr = os.getenv("ALERT_EMAIL_TO", user)

    if not host or not user or not password or not to_addr:
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


if __name__ == "__main__":
    import sys

    subject = sys.argv[1] if len(sys.argv) > 1 else "Backup"
    body = sys.argv[2] if len(sys.argv) > 2 else "Backup finished"
    send(subject, body)
