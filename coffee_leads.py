import os
import csv
import smtplib
from email.message import EmailMessage
from imapclient import IMAPClient
import pyzmail
from datetime import datetime
from dotenv import load_dotenv
import ssl
import time
import re
import requests
from bs4 import BeautifulSoup
import random

try:
    import duckduckgo_search
    DDG_AVAILABLE = True
    print("[INFO] DuckDuckGo search module loaded successfully.")
except ImportError:
    DDG_AVAILABLE = False
    print("[WARNING] duckduckgo_search module not found. Install with 'pip install duckduckgo-search'.")

load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "dsvcommodities@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
print(f"[INFO] Loaded credentials: EMAIL_SENDER={EMAIL_SENDER}, PASSWORD={'*' * len(EMAIL_PASSWORD) if EMAIL_PASSWORD else 'None'}")

IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

LOG_FILE = "email_leads_log.csv"
FAILED_ENRICH_LOG = "enrichment_failures.csv"

B2B_SITES = ["alibaba.com", "globalsources.com", "made-in-china.com", "exporthub.com", "ec21.com", "kompass.com"]
GENERIC_FILTERS = ['info@', 'support@', 'no-reply@', 'gmail.com', 'yahoo.com', 'hotmail.com']


def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Timestamp", "Email", "Source URL", "Status"])


def scrape_emails_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        page_text = response.text
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}", page_text)
        valid_emails = []
        for email in emails:
            email = email.rstrip('.').lower()
            if (re.match(r"[^@]+@[^@]+\\.[a-zA-Z]{2,}", email) and
                not any(generic in email for generic in GENERIC_FILTERS) and
                not email.endswith(('.png', '.jpg', '.jpeg', '.gif'))):
                valid_emails.append(email)
        return list(set(valid_emails))
    except:
        return []


def is_within_monthly_limit(email):
    if not os.path.exists(LOG_FILE):
        return True
    with open(LOG_FILE, "r", newline="") as csvfile:
        reader = csv.reader(csvfile)
        next(reader, None)
        count = 0
        today = datetime.now()
        for row in reader:
            if row[1].lower() == email.lower() and row[0]:
                sent_date = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f")
                if (today - sent_date).days < 30:
                    count += 1
            if count >= 2:
                return False
        return True


def extract_company_name(title):
    if "|" in title:
        return title.split("|")[0].strip()
    return title.strip()


def secondary_email_search(company_name):
    retries = 3
    for attempt in range(retries):
        try:
            time.sleep(random.uniform(10, 30))
            query = f'"{company_name}" email contact site:.com'
            with duckduckgo_search.DDGS() as ddgs:
                results = ddgs.text(query, max_results=5)
                for res in results:
                    href = res.get("href")
                    if href:
                        emails = scrape_emails_from_url(href)
                        if emails:
                            return emails[0], href
            return None, None
        except Exception as e:
            print(f"[ERROR] Email enrichment failed on attempt {attempt + 1}: {str(e)}")
            time.sleep(5 * (attempt + 1))
    return None, None


def global_email_scraper():
    if not DDG_AVAILABLE:
        print("[ERROR] Global email scraping skipped due to missing duckduckgo_search module.")
        return []
    leads = []
    seen_emails = set()
    region_priority = ["North America", "Europe", "Asia", "Australia", "Africa"]
    for region in region_priority:
        query = f"coffee bean buyers {region} email contact -South America"
        print(f"[SEARCH] Querying: {query}")
        try:
            with duckduckgo_search.DDGS() as ddgs:
                results = ddgs.text(query, max_results=15)
                for r in results:
                    url = r.get("href")
                    title = r.get("title", "")
                    if not url:
                        continue
                    emails = scrape_emails_from_url(url)
                    if emails:
                        for email in emails:
                            if is_within_monthly_limit(email) and (email, url) not in seen_emails:
                                leads.append((email, url))
                                seen_emails.add((email, url))
                    else:
                        company_name = extract_company_name(title)
                        print(f"[INFO] Extracted company name: {company_name}")
                        email, enriched_url = secondary_email_search(company_name)
                        if email and is_within_monthly_limit(email) and (email, enriched_url) not in seen_emails:
                            leads.append((email, enriched_url))
                            seen_emails.add((email, enriched_url))
                        elif not email:
                            with open(FAILED_ENRICH_LOG, "a") as f:
                                f.write(f"{company_name},{url}\n")
        except Exception as e:
            print(f"[ERROR] Scraping failed: {str(e)}")
    return leads


def send_email(recipient, attachment_path, source_url):
    if not os.path.exists(attachment_path):
        print(f"[ERROR] Attachment {attachment_path} not found.")
        return
    try:
        msg = EmailMessage()
        msg['Subject'] = "Premium Coffee Beans Offer from D.S.V Commodities"
        msg['From'] = EMAIL_SENDER
        msg['To'] = recipient
        msg.set_content(
            """Dear buyer,

Please find attached our coffee bean product catalog. Let us know if you're interested.

You can also contact us on Telegram: https://t.me/DSVcommodities
Or WhatsApp: +256783282878
Visit our website for more details: https://dvyne982.github.io/dsv-commodities/

Best regards,
D.S.V Commodities"""
        )
        with open(attachment_path, 'rb') as f:
            msg.add_attachment(f.read(), maintype='application', subtype='pdf', filename='product_details.pdf')

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)

        log_email_activity(recipient, source_url, "SENT")
        print(f"[SUCCESS] Email sent to {recipient}")
        time.sleep(5)

    except Exception as e:
        print(f"[FAIL] Failed to send email to {recipient}: {str(e)}")
        log_email_activity(recipient, source_url, f"FAILED: {str(e)}")


def log_email_activity(email, url, status):
    with open(LOG_FILE, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([datetime.now(), email, url, status])


def check_inbox_and_reply():
    try:
        with IMAPClient(IMAP_SERVER, ssl=True) as client:
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
                    """Thank you for your interest in our coffee beans. We'll get back to you shortly.

For faster communication, you can also reach us on Telegram: https://t.me/DSVcommodities
or WhatsApp: +256783282878.
Visit our website for more details: https://dvyne982.github.io/dsv-commodities/

Best regards,
D.S.V Commodities"""
                )

                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
                    smtp.starttls()
                    smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
                    smtp.send_message(reply)

                client.add_flags(uid, ['\\Seen'])
                log_email_activity(sender, "reply", "REPLIED")
                print(f"[REPLIED] Auto-response sent to {sender}")
                time.sleep(5)

    except Exception as e:
        print(f"[ERROR] Failed to check inbox: {str(e)}")


if __name__ == "__main__":
    print("[START] Coffee Leads System Running...")
    initialize_log()
    scraped_leads = global_email_scraper()
    attachment_path = "static/Coffee_media/product_details.pdf"
    for email, url in scraped_leads:
        print(f"[PROCESS] Sending to {email} from {url}")
        send_email(email, attachment_path, url)
    check_inbox_and_reply()
    print("[DONE] All tasks completed.")
