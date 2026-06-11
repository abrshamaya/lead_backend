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
    Thin wrapper for Django Q scheduling.  Django Q serialises task args, and
    passing a full Django model instance can be unreliable.  This function
    accepts primitive types and does the DB lookup itself so it's safe to
    schedule via django_q.tasks.schedule().
    """
    from amaya_api.models import Lead
    lead = Lead.objects.get(place_id=place_id)
    make_outbound_call(lead, to_number)


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
