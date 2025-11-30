from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import imaplib
import email
from datetime import timezone,datetime
from typing import TypedDict, List
import re
from email.utils import parsedate_to_datetime, parseaddr

def send_mail_to_lead(lead_email, business_name):
    subject = f"Insurance coverage for {business_name}"

    if not lead_email:
        raise Exception("No Email Given")


    print("Attempting to send email...")
    print(f"From: {settings.DEFAULT_FROM_EMAIL}")
    print(f"To: {lead_email}")
    context = {
        "subject": f"Business insurance options for {business_name}",
        "recipient_business_name": f"{business_name}",
        "company_name": "Amaya Insurance Co.",
        "company_address": "500 Market Street, New York, NY 10001",
        "license_number": "LIC-1234567",
        "phone": "+15712772462",
        "product_name": "Business Liability and Property Coverage",
        "logo_url": "https://cdn.securesure.com/logo.png",
        "cta_url": "https://securesure.com/quote/?lead_id=abc123",
        "unsubscribe_url": "https://securesure.com/unsubscribe/",
    }
    plain_msg = render_to_string("email_template.txt", context)
    html_msg = render_to_string("email_template.html", context)

    try:
        send_mail(
            subject=subject,
            message=plain_msg,
            from_email = settings.DEFAULT_FROM_EMAIL,
            recipient_list=[lead_email],
            fail_silently=False,
            html_message=html_msg
        )
 
    except Exception as e:
        raise Exception("Failed to send email ", str(e))

pattern = re.compile(r"^(.*?)(?:\bOn\b.*)?$", re.DOTALL)

class Message(TypedDict):
    msg:str
    date:datetime
    sender_name:str
    sender_email:str
    receiver_email:str

def safe_date(msg):
    d = parsedate_to_datetime(msg)

    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)

    return d

def get_plain_text(msg):
    """
    msg = email.message.Message object (from message_from_bytes)
    returns only the plain text content, no HTML, no attachments
    """
    if not msg.is_multipart():
        if msg.get_content_type() == "text/plain":
            plain_msg =  msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors="replace")
            m = pattern.match(plain_msg)
            if m:
                return m.group(1).replace("\r\n","\n").replace("\r", "\n").strip()
        return ""

    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))
        # Skip attachments
        if "attachment" in content_disposition:
            continue

        # We only care about plain text
        if content_type == "text/plain":
            charset = part.get_content_charset() or "utf-8"
            plain_msg = part.get_payload(decode=True).decode(charset, errors="replace")
            m = pattern.match(plain_msg)
            if m:
                return m.group(1).replace("\r\n","\n").replace("\r", "\n").strip()

    return ""   # no text/plain found

def get_conversation(other_email:str)->List[Message]:
    imap = imaplib.IMAP4_SSL(settings.EMAIL_IMAP_HOST)
    self_email = settings.EMAIL_HOST_USER
    try:
        imap.login(self_email,settings.EMAIL_HOST_PASSWORD)
        imap.select('"[Gmail]/Sent Mail"')
    except Exception as e:
        print(str(e))
        return []
    status,data = imap.search(None, f'TO "{other_email}"')
    if status != 'OK':
        return []

    conv:List[Message] = []

    # Storing every message we have sent to the given user
    
    for m_id in data[0].split():
        status, msg_data = imap.fetch(m_id,'(RFC822)')
        if status != "OK":
            continue
        byytes = msg_data[0][1]
        msg = email.message_from_bytes(byytes)
        sender_name, sender_email = parseaddr(msg["From"])

        plain_msg = get_plain_text(msg)
        if plain_msg:
            conv.append({"msg": plain_msg,"date": safe_date(msg["Date"]),"sender_name":sender_name, "sender_email":sender_email,"receiver_email":other_email})

    
    # Logging everything recieved
    imap.select("INBOX")
    status, data = imap.search(None, f'FROM "{other_email}"')
    for m_id in data[0].split():
        status, msg_data = imap.fetch(m_id, '(RFC822)')
        if status != "OK":
            continue
        byytes = msg_data[0][1]
        msg = email.message_from_bytes(byytes)
        plain_msg = get_plain_text(msg)
        sender_name, sender_email = parseaddr(msg["From"])
        if plain_msg:
            conv.append({"msg": plain_msg,"date": safe_date(msg["Date"]),"sender_name":sender_name, "sender_email":sender_email,"receiver_email":self_email})

    # Sorting based on date
    conv.sort(key=lambda m: m['date'])
   
    imap.close()
    imap.logout()


    return conv



def send_email(lead_email,bussiness_name, message):
    if not lead_email:
        raise Exception("No Email Given")

    if not message:
        raise Exception("No Message Provided")

    print("Attempting to send email...")
    print(f"From: {settings.DEFAULT_FROM_EMAIL}")
    print(f"To: {lead_email}")

    try:
        send_mail(
            subject="",   # no subject
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[lead_email],
            fail_silently=False
        )
    except Exception as e:
        raise Exception("Failed to send email", str(e))


