import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(message): # add timing

    # Sender and receiver info
    sender_email = "florian.jule@gadz.org"
    receiver_email = "florian.jule@gadz.org"
    password = "fdbxhbutntmzdqvq"

    # Email content
    # for content in message:
    #     street = 
    street = ''
    schedule = ''
    subject = "Street parking"
    body = message

    # Set up MIME
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    # Send email via Gmail's SMTP server
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error: {e}")

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
