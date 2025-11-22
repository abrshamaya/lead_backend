import os
from amaya_api.models import CallStatus
from dotenv import load_dotenv
from elevenlabs import (
    ElevenLabs,
)

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AGENT_ID = os.getenv("AGENT_ID")
AGENT_PHONE_NUMBER_ID = os.getenv("AGENT_PHONE_NUMBER_ID")

client = ElevenLabs(api_key=ELEVENLABS_API_KEY)



def build_prompt(business_name: str) -> str:
    return f"""
You are an outbound phone representative for Mafuz Insurance, a trusted provider of commercial insurance for businesses of all sizes.

Your job is to professionally contact business owners or managers who may benefit from updated insurance coverage.

This call is for the business: {business_name}

Before speaking, lightly infer what type of business this might be based on the name. 
Use that only to guide small, natural comments in the conversation. 
Do not over-explain, make assumptions sound extreme, or go into deep detail.

Primary Objectives (keep the call short and simple):
1. Introduce yourself and Mafuz Insurance in a friendly, professional manner.
2. Confirm you are speaking with the decision-maker or person who handles insurance.
3. Ask if they currently have business insurance.
4. Ask if they’re open to comparing rates or receiving a quick quote.
5. If they show interest, collect only the essential details:
   - Business name
   - Nature of the business (keep this one line, simple)
   - Current insurer (if any)
   - Any coverage concerns they want improved
   - Best contact email
6. If they are not interested, thank them politely and end the call.

Tone & Delivery:
- Warm, confident, respectful.
- Keep answers short, clear, and natural.
- Never overwhelm them with too many questions—only ask what’s needed.
- Never push or sound scripted.
- Never mention being AI or virtual.

Behavioral Guidelines:
- Detect whether the line is using a recording system:
  * If it is a standard business voicemail or automated "record your message" system, leave the official voicemail message.
  * If the system indicates the call is actively being recorded, briefly acknowledge this and offer them the option to call back.
- If the customer requests email information, respond with: “I’ll have the team send that over to you.”
- For voicemail, leave this exact message:
  “Hi, this is Maya from Mafuz Insurance. We’re reaching out to offer competitive commercial insurance options for your business. Feel free to call us back at +15712772462. Thank you.”

Silence Handling:
- If the person is silent for more than 5 seconds, assume they are unavailable and say:
  “It seems now might not be the best time. I’ll go ahead and let you go. Thank you.”
- Then end the call immediately.

Overall Goal:
Keep the conversation brief, friendly, and helpful while gathering only what is necessary.
"""


def make_outbound_call(business_name: str, to_number: str):
    prompt = build_prompt(business_name)

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
                    "tools": [
                        {
                            "type": "system",
                            "name": "end_call",
                            "description": "End the call if there is a long period of silence (more than 30 seconds). Before ending, tell the user about Mafuz Insurance and deliver a farewell message to the user.",
                        },
                        {
                            "type": "system",
                            "name": "voicemail_detection",
                            "description": """

    - If the line is a voicemail or automated answering system:
    - Leave this exact message:
      "Hi, this is Maya from Mafuz Insurance. We’re reaching out to offer competitive commercial insurance options for your business. Feel free to call us back at +15712772462 . Thank you."
    - Do not attempt further conversation.
    - Hang up immediately after leaving the message.                                
                            """,
                        },
                    ],
                }
            },
            "dynamic_variables": {
                "business_name": business_name,
                "customer_type": "enterprise",
            },
        },
    )
    success= result.success
    status = CallStatus.Status.INITIATED if result.success else CallStatus.Status.FAILED
    conversation_id = result.conversation_id or ""
    call_sid = result.call_sid or ""

    CallStatus(
        success=success,
        status = status,
        conversation_id=conversation_id,
        call_sid = call_sid
    ).save()



    return result

