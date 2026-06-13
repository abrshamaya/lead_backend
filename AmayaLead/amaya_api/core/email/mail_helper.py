from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import escape
from django.conf import settings
import imaplib
import email
import base64
import uuid
from email.mime.image import MIMEImage
from datetime import timezone,datetime
from typing import TypedDict, List
import re
from email.utils import parsedate_to_datetime, parseaddr


def brand_context() -> dict:
    """Shared branding for all outbound emails — self-hosted logo + agency
    contact details. Colours live in the templates (#174275 navy / #4b8b61 green)."""
    base = getattr(settings, "FRONTEND_URL", "https://remedylead.app").rstrip("/")
    return {
        "company_name": "Mahfuz Insurance Agency",
        "company_address": "6000 Stevenson Ave suite 303, Alexandria VA 22304",
        "phone": "703-212-9131",
        "email": "mummedm@mahfuzinsagency.com",
        "logo_url": f"{base}/static/email/mahfuz-logo.png",
        "unsubscribe_url": "https://www.mahfuzinsagency.com/unsubscribe/",
    }

# Images smaller than this are almost always tracking pixels / spacer gifs and
# are skipped when extracting attachments for display.
MIN_IMAGE_BYTES = 2048

def send_mail_to_lead(lead_email, business_name):
    subject = f"Insurance coverage for {business_name}"

    if not getattr(settings, 'EMAIL_SENDING', True):
        print(f"EMAIL_SENDING disabled — skipping email to {lead_email} ({business_name})")
        return

    if not lead_email:
        raise Exception("No Email Given")

# Mahfuz Insurance Agency
# 6000 Stevenson Ave suite 303
# Alexandria VA 22304
# Telephone: 703-212-9131
# mummedm@mahfuzinsagency.com

    print("Attempting to send email...")
    print(f"From: {settings.DEFAULT_FROM_EMAIL}")
    print(f"To: {lead_email}")
    context = {
        **brand_context(),
        "subject": f"Business insurance options for {business_name}",
        "recipient_business_name": f"{business_name}",
        "license_number": "LIC-1234567",
        "product_name": "Business Liability and Property Coverage",
        "cta_url": "https://shortifyme.co/4QQYO",
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


class ImageAttachment(TypedDict):
    filename: str
    data_uri: str  # "data:image/png;base64,…"


class Message(TypedDict):
    msg: str
    date: str  # ISO format string (e.g., "2024-01-15T10:30:00+00:00")
    sender_name: str
    sender_email: str
    receiver_email: str
    images: List[ImageAttachment]


def get_message_images(msg) -> List[ImageAttachment]:
    """Extract image attachments / inline images from an email message and
    return them as base64 data URIs so the frontend can render them inline."""
    images: List[ImageAttachment] = []
    if not msg.is_multipart():
        return images
    for part in msg.walk():
        ctype = part.get_content_type()
        if not ctype.startswith("image/"):
            continue
        payload = part.get_payload(decode=True)
        if not payload or len(payload) < MIN_IMAGE_BYTES:
            continue
        b64 = base64.b64encode(payload).decode("ascii")
        ext = ctype.split("/")[-1]
        filename = part.get_filename() or f"image.{ext}"
        images.append({"filename": filename, "data_uri": f"data:{ctype};base64,{b64}"})
    return images


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
        images = get_message_images(msg)
        if plain_msg or images:
            conv.append({"msg": plain_msg,"date": safe_date(msg["Date"]),"sender_name":sender_name, "sender_email":sender_email,"receiver_email":other_email,"images":images})

    
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
        images = get_message_images(msg)
        sender_name, sender_email = parseaddr(msg["From"])
        if plain_msg or images:
            conv.append({"msg": plain_msg,"date": safe_date(msg["Date"]),"sender_name":sender_name, "sender_email":sender_email,"receiver_email":self_email,"images":images})

    # Sorting based on date
    conv.sort(key=lambda m: m['date'])
   
    imap.close()
    imap.logout()


    return conv



def send_email(lead_email, bussiness_name, message, subject="", attachments=None):
    """Send a reply to a lead. `attachments` is an optional list of
    {filename, content_type, data} dicts where `data` is base64-encoded bytes
    (e.g. an image edited in the chat composer)."""
    if not getattr(settings, 'EMAIL_SENDING', True):
        print(f"EMAIL_SENDING disabled — skipping email to {lead_email} ({bussiness_name})")
        return

    if not lead_email:
        raise Exception("No Email Given")

    attachments = attachments or []
    if not message and not attachments:
        raise Exception("No Message Provided")

    print("Attempting to send email...")
    print(f"From: {settings.DEFAULT_FROM_EMAIL}")
    print(f"To: {lead_email}")

    if not subject:
        subject = f"Re: Insurance coverage for {bussiness_name}" if bussiness_name else "Re: Insurance coverage"

    try:
        ctx = brand_context()
        ctx["subject"] = subject

        # Attach images inline (cid:) so they render in the HTML body, not just
        # as downloads. Gmail strips data: URIs, so we use Content-ID references.
        inline_imgs = []   # (cid, raw_bytes, subtype, filename)
        cid_srcs = []
        for att in attachments:
            raw = att.get("data", "")
            if not raw:
                continue
            subtype = (att.get("content_type") or "image/jpeg").split("/")[-1]
            cid = uuid.uuid4().hex
            inline_imgs.append((cid, base64.b64decode(raw), subtype, att.get("filename") or f"image.{subtype}"))
            cid_srcs.append(f"cid:{cid}")

        text_body = render_to_string("reply_template.txt", {**ctx, "message": message or ""})
        html_body = render_to_string("reply_template.html", {
            **ctx,
            "message_html": escape(message or "").replace("\n", "<br>"),
            "images": cid_srcs,
        })

        email_msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[lead_email],
        )
        email_msg.attach_alternative(html_body, "text/html")
        if inline_imgs:
            email_msg.mixed_subtype = "related"   # bind inline images to the HTML
            for cid, raw_bytes, subtype, filename in inline_imgs:
                img = MIMEImage(raw_bytes, _subtype=subtype)
                img.add_header("Content-ID", f"<{cid}>")
                img.add_header("Content-Disposition", "inline", filename=filename)
                email_msg.attach(img)
        email_msg.send(fail_silently=False)
    except Exception as e:
        raise Exception("Failed to send email", str(e))


