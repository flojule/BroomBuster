import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config


def send_email(message):
    """Send a street-sweeping notification email using credentials from config/env."""
    if not config.EMAIL_SENDER or not config.EMAIL_PASSWORD:
        print("Email credentials not configured — skipping notification.")
        return

    msg = MIMEMultipart()
    msg["From"]    = config.EMAIL_SENDER
    msg["To"]      = config.EMAIL_RECEIVER or config.EMAIL_SENDER
    msg["Subject"] = "Street parking alert"
    msg.attach(MIMEText(message, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("Notification email sent.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def compose_message(schedule_even, schedule_odd, car_side):
    """Return a plain-text schedule summary matching the map info panel layout."""

    def _fmt_plain(entries, label, highlight):
        valid = [e for e in entries if e and len(e) >= 3]
        prefix = "►" if highlight else " "
        if not valid:
            return f"{prefix} {label}: no sweeping"
        seen = set()
        parts = []
        for entry in valid:
            key = (entry[1], entry[2])
            if key not in seen:
                t = entry[2]
                body = entry[1] if not t else f"{entry[1]} \u2014 {t}"
                parts.append(body)
                seen.add(key)
        return f"{prefix} {label}: {' / '.join(parts)}"

    even_line = _fmt_plain(schedule_even, "Even side", highlight=(car_side == "even"))
    odd_line  = _fmt_plain(schedule_odd,  "Odd side",  highlight=(car_side == "odd"))
    return f"{even_line}\n{odd_line}"
