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

def compose_message(myStreetName, myNumber, myStreets, schedule):

    schedule_ = [x[1:] for x in schedule]
    schedule_text = '\n'.join([f"{x[0]}, {x[1]}" for x in schedule_])

    if myStreetName == myStreets[0]:
        message = f"The car nearest address is: {myNumber} {myStreetName}\nThis is the schedule for that side of the street:\n{schedule_text}"
    elif myStreetName == myStreets[1]:
        message = f"The car nearest address is: {myNumber} {myStreetName}\nThe car nearest street is: {myStreets[0]}\nThe nearest street does not match nearest address\n\nThis is the schedule for the street:\n {schedule_text}"
    else:
        message = f"There is a problem, check the data"

    return message
