import os
from amaya_api.models import CallStatus, Lead, CallConversations
from dotenv import load_dotenv
from elevenlabs import ElevenLabs

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AGENT_ID = os.getenv("AGENT_ID")
AGENT_PHONE_NUMBER_ID = os.getenv("AGENT_PHONE_NUMBER_ID")
CALLBACK_NUMBER = "+15712772462"

client = ElevenLabs(base_url="https://api.elevenlabs.io/", api_key=ELEVENLABS_API_KEY)


def make_outbound_call(lead: Lead, to_number: str):
    business_name = str(lead.name) if lead.name else ""

    print(f"[call] ▶ Initiating call → {business_name} ({to_number})")
    print(f"[call]   agent_id={AGENT_ID}  phone_number_id={AGENT_PHONE_NUMBER_ID}")

    # The agent's first message, system prompt, and tools are configured in the
    # ElevenLabs dashboard (see ELEVENLABS_AGENT_CONFIG.md) — overrides are
    # disallowed by the agent's security config. We only inject dynamic
    # variables, which the dashboard prompt references as {{business_name}} etc.
    try:
        result = client.conversational_ai.twilio.outbound_call(
            agent_id=AGENT_ID,
            agent_phone_number_id=AGENT_PHONE_NUMBER_ID,
            to_number=to_number,
            conversation_initiation_client_data={
                "dynamic_variables": {
                    "business_name": business_name,
                    "callback_number": CALLBACK_NUMBER,
                    "customer_type": "enterprise",
                },
            },
        )
    except Exception as exc:
        print(f"[call] ✗ ElevenLabs API error: {exc}")
        raise

    success = result.success
    status = CallConversations.Status.INITIATED if result.success else CallConversations.Status.FAILED
    conversation_id = result.conversation_id or ""
    call_sid = result.call_sid or ""
    print(f"[call] {'✓' if success else '✗'} success={success}  conversation_id={conversation_id}  call_sid={call_sid}")
    if not success:
        msg = getattr(result, 'message', None) or 'ElevenLabs returned success=False'
        print(f"[call] ✗ Full result object: {vars(result) if hasattr(result, '__dict__') else result}")
        raise RuntimeError(f"Call failed: {msg}")

    CallConversations(
        lead=lead,
        success=success,
        status=status,
        conversation_id=conversation_id,
        call_sid=call_sid,
    ).save()

    return result


def schedule_outbound_call(place_id: str, to_number: str):
    """
    Django Q task entrypoint for outbound calls (immediate via async_task and
    deferred via schedule()).  Accepts primitive types because Django Q
    serialises task args.  Marks the lead, fires notifications, and re-raises
    on failure so the task is recorded as failed in the task list.
    """
    from amaya_api.models import Lead
    from amaya_api.core.notifications import notify_call_initiated, notify_call_failed
    lead = Lead.objects.get(place_id=place_id)
    try:
        result = make_outbound_call(lead, to_number)
    except Exception:
        try:
            notify_call_failed(lead, "")
        except Exception:
            pass
        raise
    lead.call_sent = True
    lead.save(update_fields=['call_sent'])
    try:
        notify_call_initiated(lead, result.conversation_id or "", to_number)
    except Exception:
        pass
    return result.conversation_id or ""


def sync_conversation_statuses(conversations) -> int:
    """Pull fresh ElevenLabs status for non-terminal conversations and fire a
    notification on the first transition into a terminal state (done/failed).
    Transient API errors leave the row untouched for the next poll.
    Returns the number of conversations updated."""
    from amaya_api.models import CallConversations
    from amaya_api.core.notifications import notify_call_completed, notify_call_failed
    updated = 0
    for conversation in conversations:
        if conversation.status in (CallConversations.Status.DONE, CallConversations.Status.FAILED):
            continue
        try:
            call_status = (
                get_conversation_status(conversation.conversation_id)
                if conversation.conversation_id else ''
            )
        except Exception as exc:
            print(f"[call] status check failed for {conversation.conversation_id}: {exc}")
            continue
        if call_status and CallConversations.is_valid_status(call_status):
            conversation.status = call_status
        else:
            conversation.status = CallConversations.Status.FAILED
        conversation.save(update_fields=['status'])
        updated += 1
        try:
            if conversation.status == CallConversations.Status.DONE:
                notify_call_completed(conversation.lead, conversation.conversation_id)
            elif conversation.status == CallConversations.Status.FAILED:
                notify_call_failed(conversation.lead, conversation.conversation_id)
        except Exception:
            pass
    return updated


def check_call_statuses_task() -> int:
    """Recurring background poller (see apps.py): keeps call conversation
    statuses fresh and produces completed/failed notifications without anyone
    having to open the lead's call history."""
    from amaya_api.models import CallConversations
    pending = CallConversations.objects.exclude(
        status__in=[CallConversations.Status.DONE, CallConversations.Status.FAILED]
    ).select_related('lead')
    return sync_conversation_statuses(pending)


def get_audio(conversation_id: str):
    return client.conversational_ai.conversations.audio.get(
        conversation_id=conversation_id
    )


def get_conversation_status(conversation_id: str):
    res = client.conversational_ai.conversations.get(
        conversation_id=conversation_id
    )
    print(f"[call] status for {conversation_id}: {res.status}")
    return res.status or ""


def get_conversation_transcript(conversation_id: str):
    """Return the call transcript as a list of {role, message, time_in_call_secs}
    turns. Roles are normalised to 'agent' / 'user'. Empty turns are skipped."""
    res = client.conversational_ai.conversations.get(
        conversation_id=conversation_id
    )
    turns = []
    for turn in (getattr(res, "transcript", None) or []):
        # SDK returns objects; fall back to dict access just in case.
        role = getattr(turn, "role", None) or (turn.get("role") if isinstance(turn, dict) else "")
        message = getattr(turn, "message", None) or (turn.get("message") if isinstance(turn, dict) else "")
        secs = getattr(turn, "time_in_call_secs", None)
        if secs is None and isinstance(turn, dict):
            secs = turn.get("time_in_call_secs")
        if not message:
            continue
        turns.append({
            "role": "agent" if role == "agent" else "user",
            "message": message,
            "time_in_call_secs": secs,
        })
    return turns
