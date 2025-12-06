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
        "company_name": "Remedy Insurance and taxes.",
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

# Pattern to match Gmail's thread markers like:
# "On Thu, Jan 15, 2024 at 10:30 AM John Doe <john@example.com> wrote:"
# "On Thursday, January 15, 2024 at 10:30 AM John Doe <john@example.com> wrote:"
# Also handles variations with different date formats
GMAIL_THREAD_PATTERN = re.compile(
    r'\n*On\s+'
    r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
    r'[,\s]+'
    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)'
    r'[^<>]*?'  # Date and time portion
    r'(?:<[^>]+>)?\s*'  # Optional email in angle brackets
    r'wrote:',
    re.IGNORECASE | re.DOTALL
)

# Alternative pattern for "On <date> at <time>, <name> wrote:"
GMAIL_THREAD_PATTERN_ALT = re.compile(
    r'\n*On\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*?wrote:',
    re.IGNORECASE | re.DOTALL
)

# Pattern for quoted lines (lines starting with >)
QUOTED_LINE_PATTERN = re.compile(r'^>.*$', re.MULTILINE)


class Message(TypedDict):
    msg: str
    date: str  # ISO format string (e.g., "2024-01-15T10:30:00+00:00")
    sender_name: str
    sender_email: str
    receiver_email: str


def safe_date(msg_date: str) -> str:
    """
    Parse email date string to ISO format string in UTC.
    
    All dates are converted to UTC to ensure correct chronological sorting,
    since ISO strings with different timezone offsets don't sort lexicographically
    in chronological order (e.g., "10:30+05:00" sorts after "06:00+00:00" even
    though 10:30+05:00 = 05:30 UTC which is earlier than 06:00 UTC).
    """
    d = parsedate_to_datetime(msg_date)

    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC for consistent sorting
        d = d.astimezone(timezone.utc)

    return d.isoformat()


def strip_gmail_thread(text: str) -> str:
    """
    Remove Gmail thread markers and quoted content from email text.
    
    Gmail adds lines like:
    "On Thursday, January 15, 2024 at 10:30 AM John Doe <john@example.com> wrote:"
    followed by the quoted previous message.
    
    This function removes that and everything after it.
    """
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Try to find Gmail thread marker and remove it + everything after
    match = GMAIL_THREAD_PATTERN.search(text)
    if match:
        text = text[:match.start()]
    else:
        # Try alternative pattern
        match = GMAIL_THREAD_PATTERN_ALT.search(text)
        if match:
            text = text[:match.start()]
    
    # Remove any remaining quoted lines (lines starting with >)
    text = QUOTED_LINE_PATTERN.sub('', text)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def get_plain_text(msg) -> str:
    """
    Extract plain text content from email message.
    
    Args:
        msg: email.message.Message object (from message_from_bytes)
    
    Returns:
        Plain text content with Gmail thread markers removed
    """
    def extract_and_clean(payload_bytes, charset: str) -> str:
        """Decode payload and clean up Gmail thread content."""
        try:
            text = payload_bytes.decode(charset or 'utf-8', errors="replace")
            return strip_gmail_thread(text)
        except Exception:
            return ""
    
    if not msg.is_multipart():
        if msg.get_content_type() == "text/plain":
            charset = msg.get_content_charset() or 'utf-8'
            payload = msg.get_payload(decode=True)
            if payload:
                return extract_and_clean(payload, charset)
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
            payload = part.get_payload(decode=True)
            if payload:
                return extract_and_clean(payload, charset)

    return ""  # no text/plain found

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


