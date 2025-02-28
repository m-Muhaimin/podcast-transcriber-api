from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import db 
import ssl
from email.mime.text import MIMEText
from apscheduler.schedulers.background import BackgroundScheduler
import time
import os 

from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file



SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT")  # Port 465 for SSL                  
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECIPIENT_EMAIL = "mahmud17321@gmail.com"

# ---------------------------
# Helper Functions
# ---------------------------

def send_email(subject: str, body: str):
    """Sends an email to the user."""
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())



def send_daily_takeaway():
    """Sends a daily email with one key takeaway from the latest podcast."""
    data = db.get_latest_podcast_data()
    if not data or not data["takeaways"]:
        print("No podcast data available for email.")
        return
    
    # Rotate through key takeaways each day

    takeaway = data["takeaways"][1]  

    email_subject = "📢 Daily Key Takeaway from Podcast"
    email_body = f"Good morning! 🌞\n\nToday's key takeaway:\n\n➡️ {takeaway}\n\nHave a great day! 🚀"
    
    send_email(email_subject, email_body)
    print("✅ Daily takeaway email sent.")



# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.add_job(send_daily_takeaway, "cron", hour=10, minute=0)
scheduler.start()

# Keep the script running
# while True:
#   time.sleep(5)


# test = send_email("Test SMTP", "SMTP Configeratuin is Successful", "RECIPIENT_EMAIL")