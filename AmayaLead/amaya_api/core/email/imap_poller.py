"""
Background task: poll Gmail INBOX for new replies from leads and
create Notification records for any we haven't seen before.

Scheduled to run every 5 minutes via Django Q (set up in apps.py).
"""
import imaplib
import email as email_lib
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime, timedelta, timezone

from django.conf import settings


def check_email_replies_task():
    """Fetch INBOX messages from the last LOOKBACK_DAYS days, match senders
    against tracked lead emails, and fire notifications for new replies."""
    from amaya_api.models import Email as LeadEmail
    from amaya_api.core.notifications import notify_email_reply

    LOOKBACK_DAYS = 3

    # Build a lookup: sender_email (lowercase) → Lead
    email_to_lead = {
        row["email"].lower(): row["business"]
        for row in LeadEmail.objects.select_related("business").values("email", "business")
    }
    if not email_to_lead:
        return  # no leads yet, nothing to check

    try:
        imap = imaplib.IMAP4_SSL(settings.EMAIL_IMAP_HOST)
        imap.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        imap.select("INBOX")
    except Exception as e:
        print(f"[imap_poller] IMAP connection failed: {e}")
        return

    since = (datetime.now(tz=timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
    status, data = imap.search(None, f'SINCE "{since}"')
    if status != "OK":
        imap.logout()
        return

    msg_ids = data[0].split()
    if not msg_ids:
        imap.logout()
        return

    # Resolve Lead FK ids to full Lead objects lazily (only when needed)
    from amaya_api.models import Lead
    lead_cache: dict = {}

    def get_lead(lead_id: int):
        if lead_id not in lead_cache:
            try:
                lead_cache[lead_id] = Lead.objects.get(pk=lead_id)
            except Lead.DoesNotExist:
                lead_cache[lead_id] = None
        return lead_cache[lead_id]

    for m_id in msg_ids:
        status, msg_data = imap.fetch(m_id, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        if not isinstance(raw, bytes):
            continue

        msg = email_lib.message_from_bytes(raw)
        _, sender_email = parseaddr(msg.get("From", ""))
        sender_email = sender_email.lower().strip()

        # Skip our own sent emails that ended up in INBOX (e.g. BCC)
        own_email = settings.EMAIL_HOST_USER.lower()
        if sender_email == own_email or sender_email not in email_to_lead:
            continue

        message_id = msg.get("Message-ID", "").strip()
        if not message_id:
            # Fall back to a composite key so we still deduplicate
            date_str = msg.get("Date", "")
            message_id = f"{sender_email}::{date_str}"

        lead_id = email_to_lead[sender_email]
        lead = get_lead(lead_id)
        if not lead:
            continue

        sender_name, _ = parseaddr(msg.get("From", ""))
        sender_name = sender_name or sender_email

        try:
            notify_email_reply(lead, sender_name, sender_email, message_id)
        except Exception as e:
            print(f"[imap_poller] Failed to create notification for {sender_email}: {e}")

    imap.close()
    imap.logout()
    print(f"[imap_poller] Checked {len(msg_ids)} inbox messages.")
