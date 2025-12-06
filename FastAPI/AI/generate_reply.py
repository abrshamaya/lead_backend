import requests
import json
import os
import re
from dotenv import load_dotenv
from typing import TypedDict, List
from datetime import datetime
import uuid

load_dotenv()

class Message(TypedDict):
    msg: str
    date: str  # ISO format string
    sender_name: str
    sender_email: str
    receiver_email: str

class AiSuggestion(TypedDict):
    id: str
    text: str

SYSTEM_PROMPT = """
You are an AI assistant helping an insurance sales representative respond to email conversations with business leads.

Your task:
- Analyze the conversation history provided.
- Generate suggested reply messages that the sales rep can send.
- The tone should be professional, helpful, and focused on building a relationship.
- Keep replies concise but personalized based on the conversation context.

Guidelines:
1. If this is a fresh outreach (no replies yet), suggest follow-up messages.
2. If the lead has responded, tailor the reply to their specific questions or concerns.
3. Focus on offering value - insurance solutions, quotes, consultations.
4. Be polite and not pushy.
5. Each suggestion should be a complete, ready-to-send message.
6. Do NOT include subject lines - only the email body.
7. Keep each suggestion under 150 words for readability.

Output Format:
- Return a JSON array of strings, where each string is a complete reply suggestion.
- Return exactly the number of suggestions requested.
- Do not include any other text, explanations, or formatting outside the JSON array.

Example Output:
["Thank you for your interest in our business insurance options. I'd be happy to schedule a quick call to discuss your specific needs and provide a tailored quote. Would Tuesday or Wednesday afternoon work for you?", "I appreciate you getting back to me! Based on what you've shared, I think our comprehensive liability package would be a great fit. I can send over some detailed information - what aspects of coverage are most important for your business?"]
"""

def generate_reply_suggestions(
    conversation: List[Message],
    business_name: str,
    our_email: str,
    lead_email: str,
    num_suggestions: int = 3
) -> List[AiSuggestion]:
    """
    Generate AI-powered reply suggestions based on conversation history.
    
    Args:
        conversation: List of Message objects representing the conversation history
        business_name: Name of the business lead
        our_email: Our current email address
        lead_email: The lead's email (used to reliably identify message direction)
        num_suggestions: Number of reply suggestions to generate (default: 3)
    
    Returns:
        List of AiSuggestion objects with id and text fields
    """
    
    # Format conversation for the prompt, clearly marking who sent each message
    formatted_conversation = []
    for msg in conversation:
        sender_email = msg.get('sender_email', '').lower()
        receiver_email = msg.get('receiver_email', '').lower()
        sender_name = msg.get('sender_name', '') or sender_email or 'Unknown'
        lead_email_lower = lead_email.lower()
        
        # Determine if this message is from us or the lead
        # Use lead_email for reliable detection (works even if our email changed)
        # - If receiver_email == lead_email, we sent this message TO the lead
        # - If sender_email == lead_email, the lead sent this message TO us
        if receiver_email == lead_email_lower:
            role = "US (Insurance Agent)"
        elif sender_email == lead_email_lower:
            role = f"LEAD ({business_name})"
        else:
            # Fallback: check our current email
            role = "US (Insurance Agent)" if sender_email == our_email.lower() else f"LEAD ({business_name})"
        
        formatted_conversation.append(f"[{msg.get('date', 'Unknown date')}] {role} - {sender_name}:\n{msg.get('msg', '')}")
    
    conversation_text = "\n\n".join(formatted_conversation) if formatted_conversation else "No conversation history yet - this is an initial outreach."
    
    user_prompt = f"""
You are replying on behalf of the insurance agent.

Lead Business Name: {business_name}
Our Email (Insurance Agent): {our_email}

Conversation History:
{conversation_text}

Please generate {num_suggestions} different reply suggestions that WE (the insurance agent) can send as the next message to the LEAD.
"""

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek/deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "temperature": 0.7,  # Some creativity for varied suggestions
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    res_json = response.json()

    choices = res_json.get("choices", [])
    if choices and "message" in choices[0]:
        content = choices[0]["message"].get("content", "[]")
    else:
        content = "[]"
    
    # Parse the JSON array from the response
    try:
        # Clean up the content - remove markdown code blocks if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        suggestions_list = json.loads(content)
        
        if not isinstance(suggestions_list, list):
            suggestions_list = []
    except json.JSONDecodeError:
        # Fallback: try to extract strings from the content
        suggestions_list = re.findall(r'"([^"]+)"', content)
    
    # Convert to AiSuggestion format
    result: List[AiSuggestion] = []
    for suggestion_text in suggestions_list[:num_suggestions]:
        result.append({
            "id": str(uuid.uuid4()),
            "text": str(suggestion_text)
        })
    
    return result

