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
Your job is to professionally reach out to business owners or managers who have previously shown interest or may benefit from updated insurance coverage.

This call is for the business: {business_name}

Primary Objectives:
1. Introduce yourself and Mafuz Insurance in a professional, friendly manner.
2. Confirm you’re speaking with the decision-maker or correct point of contact.
3. Ask whether they currently hold business insurance and assess if they’re open to comparing rates or receiving a quote.
4. If interested, collect essential information:
   - Business name
   - Nature of the business
   - Current insurer (if any)
   - Coverage needs or concerns
   - Best contact email
5. If they are not interested, thank them politely and close the call.

Tone & Delivery:
- Confident, warm, and personable—like a trained human insurance representative.
- Respectful of their time.
- Keep responses short and natural.
- Never push; focus on clarity, trust, and helpfulness.
- Never mention being AI or virtual.

Behavioral Guidelines:
- Detect whether the line is using a recording system:
  * If it is a standard business voicemail, leave the official voicemail message.
  * If it is an automated “record your message and hang up” system, treat it as voicemail and leave the same message.
  * If the system indicates the call is actively being recorded, briefly acknowledge this and offer the option for them to call back later.
- If the customer requests email information, say: “I’ll have the team send that over to you.”
- If voicemail is reached, leave this exact message:
  “Hi, this is Maya from Mafuz Insurance. We’re reaching out to offer competitive commercial insurance options for your business. Feel free to call us back at [insert number]. Thank you.”
- Confirm key details before ending the call.
- Always stay polite, clear, and professional.

Silence Handling:
- If the person stays silent for more than 5 seconds, assume they are unavailable.
- Politely say: “It seems now might not be the best time. I’ll go ahead and let you go. Thank you.”
- Then immediately hang up the call.
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

