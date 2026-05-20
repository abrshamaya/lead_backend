"""
Central helpers for creating Notification records.
Import these wherever an event should produce a notification.
"""
from amaya_api.models import Notification, Lead


def notify_email_reply(lead: Lead, sender_name: str, sender_email: str, message_id: str):
    """Call when we detect a new email reply from a lead via IMAP."""
    # Deduplicate by Message-ID so re-running the poller never double-notifies
    if Notification.objects.filter(metadata__message_id=message_id).exists():
        return
    Notification.objects.create(
        type=Notification.Type.EMAIL_REPLY,
        lead=lead,
        title=f"New reply from {lead.name}",
        body=f"{sender_name} <{sender_email}> replied to your email.",
        metadata={
            "email": sender_email,
            "sender_name": sender_name,
            "message_id": message_id,
        },
    )


def notify_call_initiated(lead: Lead, conversation_id: str, phone_number: str):
    Notification.objects.create(
        type=Notification.Type.CALL_INITIATED,
        lead=lead,
        title=f"Call started with {lead.name}",
        body=f"Outbound call to {phone_number} has been initiated.",
        metadata={"conversation_id": conversation_id, "phone_number": phone_number},
    )


def notify_call_completed(lead: Lead, conversation_id: str):
    Notification.objects.create(
        type=Notification.Type.CALL_COMPLETED,
        lead=lead,
        title=f"Call completed with {lead.name}",
        body="The AI call finished successfully.",
        metadata={"conversation_id": conversation_id},
    )


def notify_call_failed(lead: Lead, conversation_id: str):
    Notification.objects.create(
        type=Notification.Type.CALL_FAILED,
        lead=lead,
        title=f"Call failed for {lead.name}",
        body="The call could not be completed.",
        metadata={"conversation_id": conversation_id},
    )


def notify_scrape_done(leads_added: int, task_name: str):
    Notification.objects.create(
        type=Notification.Type.SCRAPE_DONE,
        lead=None,
        title="Scraping complete",
        body=f"Found {leads_added} new lead{'s' if leads_added != 1 else ''} for '{task_name}'.",
        metadata={"leads_added": leads_added, "task_name": task_name},
    )
