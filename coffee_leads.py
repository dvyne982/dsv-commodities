import os
import csv
import smtplib
from email.message import EmailMessage
from imapclient import IMAPClient
import pyzmail
from datetime import datetime
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
IMAP_SERVER = "imap.protonmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

LOG_FILE = "email_leads_log.csv"

# Send product offer email
def send_email(recipient, attachment_path, source_url):
    msg = EmailMessage()
    msg['Subject'] = "Premium Coffee Beans Offer from D.S.V Commodities"
    msg['From'] = EMAIL_SENDER
    msg['To'] = recipient

    msg.set_content(
        """
        Dear buyer,

        Please find attached our coffee bean product catalog. Let us know if you're interested.

        You can also contact us on Telegram: https://t.me/DSVcommodities
        Or WhatsApp: +256783282878

        Best regards,
        D.S.V Commodities
        """
    )

    with open(attachment_path, 'rb') as f:
        msg.add_attachment(f.read(), maintype='application', subtype='pdf', filename='product_details.pdf')

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)

    log_email_activity(recipient, source_url, "SENT")

# Log email actions
def log_email_activity(email, url, status):
    with open(LOG_FILE, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([datetime.now(), email, url, status])

# Check inbox and auto-respond to replies
def check_inbox_and_reply():
    with IMAPClient(IMAP_SERVER) as client:
        client.login(EMAIL_SENDER, EMAIL_PASSWORD)
        client.select_folder("INBOX", readonly=False)
        messages = client.search(['UNSEEN'])

        for uid in messages:
            raw = client.fetch([uid], ['BODY[]', 'FLAGS'])
            msg = pyzmail.PyzMessage.factory(raw[uid][b'BODY[]'])
            subject = msg.get_subject()
            sender = msg.get_addresses('from')[0][1]

            reply = EmailMessage()
            reply['Subject'] = "Re: " + subject
            reply['From'] = EMAIL_SENDER
            reply['To'] = sender

            reply.set_content(
                """
                Thank you for your interest in our coffee beans. We'll get back to you shortly.

                For faster communication, you can also reach us on Telegram: https://t.me/DSVcommodities
                or WhatsApp: +256783282878.

                Best regards,
                D.S.V Commodities
                """
            )

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
                smtp.starttls()
                smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
                smtp.send_message(reply)

            client.add_flags(uid, ['\\Seen'])
            log_email_activity(sender, "reply", "REPLIED")

# Example usage:
# send_email("buyer@example.com", "product_details.pdf", "https://example.com/contact-page")
# check_inbox_and_reply()
