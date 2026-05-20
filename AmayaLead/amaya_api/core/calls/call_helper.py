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


def build_prompt(business_name: str) -> str:
    return f"""You are Maya, a professional outbound phone representative for Mafuz Insurance.

This call is for: {business_name}

==== PRIMARY OBJECTIVES ====
1. Introduce yourself as Maya from Mafuz Insurance — briefly.
2. Confirm you are speaking with the decision-maker or person who handles insurance.
3. Ask if they currently have business insurance and if they'd be open to comparing rates.
4. If interested: collect business name, type of business, current insurer (if any), coverage concerns, best contact email.
5. If not interested: thank them, then IMMEDIATELY USE THE end_call TOOL — do not linger.

==== WHEN TO USE end_call TOOL ====
You MUST invoke the end_call tool (not just say goodbye) in ALL of these situations:
- The person says they are not interested or asks you to stop calling
- You have finished leaving a voicemail — call end_call immediately after the message ends
- Silence lasts more than 5 seconds — say "It seems now isn't a good time, I'll let you go. Have a great day." then call end_call
- You detect an IVR, automated phone tree, or hold music — call end_call immediately, do not press any buttons
- The call has had no human response after 15 seconds
- You have successfully collected all needed information — say goodbye then call end_call

==== AUTOMATED SYSTEM & IVR DETECTION ====
If you hear ANY of the following, use the voicemail_detection tool immediately:
- "Press 1 for...", "For [department] press [number]", any button-press prompts
- "Please hold", "Your call is being transferred", "Your call is important to us"
- Hold music or silence followed by music
- A pre-recorded announcement or robotic/synthesized voice
- "This call may be recorded for quality purposes"
- Any repeated automated loop or prompt
Do NOT attempt to navigate phone trees. Do NOT press any numbers. Use voicemail_detection, then end_call.

==== VOICEMAIL / ANSWERING MACHINE ====
If you reach voicemail or an answering machine:
1. Wait for the beep.
2. Leave ONLY this exact message:
   "Hi, this is Maya from Mafuz Insurance. We're reaching out about commercial insurance options for {business_name}. Please call us back at {CALLBACK_NUMBER}. Thank you."
3. USE end_call TOOL IMMEDIATELY after finishing — do not say anything else, do not wait.

==== SILENCE HANDLING ====
If the person is silent for more than 5 seconds:
1. Say: "It seems now isn't a good time. I'll let you go — have a great day."
2. USE end_call TOOL IMMEDIATELY.

==== TONE & RULES ====
- Warm, confident, respectful. Keep it short.
- Never mention being AI, a bot, or virtual.
- Never overwhelm with questions — one at a time.
- If asked for email info: "I'll have the team send that over to you."
- Keep the entire call under 3 minutes.
"""


# Tool definitions are separated so they're easy to update independently
_TOOLS = [
    {
        "type": "system",
        "name": "end_call",
        "description": (
            "USE THIS TOOL TO ACTUALLY HANG UP THE CALL. "
            "Saying goodbye is not enough — you must invoke this tool to end the call. "
            "Trigger it in ANY of these situations: "
            "(1) after 5 seconds of silence — say a short farewell first, then invoke; "
            "(2) immediately after finishing a voicemail message — no delay; "
            "(3) when the person says they are not interested — say thank you, then invoke; "
            "(4) after successfully collecting all needed information — say goodbye, then invoke; "
            "(5) when an IVR, phone tree, hold music, or automated system is detected — invoke immediately; "
            "(6) if no human has responded after 15 seconds. "
            "Do not wait, do not repeat yourself — just invoke the tool."
        ),
    },
    {
        "type": "system",
        "name": "voicemail_detection",
        "description": (
            "USE THIS TOOL to detect and handle voicemail and automated phone systems. "
            "Trigger immediately when you detect: "
            "(1) a voicemail greeting or answering machine beep; "
            "(2) IVR or phone tree prompts ('Press 1 for...', 'For X press Y'); "
            "(3) hold music or 'please hold' messages; "
            "(4) pre-recorded automated announcements or synthesized voices; "
            "(5) no human response after 10 seconds of the call connecting. "
            "On voicemail/answering machine: wait for the beep, leave the pre-approved message, "
            "then invoke end_call immediately. "
            "On IVR/phone tree: invoke end_call immediately — do NOT press any buttons."
        ),
    },
]


def make_outbound_call(lead: Lead, to_number: str):
    business_name = str(lead.name) if lead.name else ""
    prompt = build_prompt(business_name)

    print(f"[call] ▶ Initiating call → {business_name} ({to_number})")
    print(f"[call]   agent_id={AGENT_ID}  phone_number_id={AGENT_PHONE_NUMBER_ID}")

    try:
        result = client.conversational_ai.twilio.outbound_call(
            agent_id=AGENT_ID,
            agent_phone_number_id=AGENT_PHONE_NUMBER_ID,
            to_number=to_number,
            conversation_initiation_client_data={
                "conversation_config_override": {
                    "agent": {
                        "first_message": (
                            f"Hi, this is Maya calling from Mafuz Insurance. "
                            f"We specialize in commercial insurance for businesses, "
                            f"and I wanted to check whether {business_name} is currently reviewing coverage "
                            f"or open to comparing rates. Do you have a moment to talk?"
                        ),
                        "prompt": {"prompt": prompt},
                        "tools": _TOOLS,
                    }
                },
                "dynamic_variables": {
                    "business_name": business_name,
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
