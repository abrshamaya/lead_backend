import requests
import json
import os
import re
from dotenv import load_dotenv

SYSTEM_PROMPT = """
You are an AI assistant designed to validate and filter email addresses.

Your task:
- Receive a list of email addresses in JSON array format.
- You will also receive the name of a business (e.g., "Moose Run Golf Course").
- Return **only the valid email addresses that belong to the given business**, preserving their original order.

Validation Rules:
1. A valid email must match the general pattern: local-part@domain.
2. The local-part may contain letters, numbers, underscores (_), periods (.), and hyphens (-), but cannot start or end with a period or contain consecutive periods.
3. The domain must contain at least one period, cannot start or end with a hyphen, and must use only letters, numbers, hyphens (-), and periods (.).
4. The top-level domain (TLD) must be at least 2 characters (e.g., .com, .org, .net, .io, etc.).
5. Exclude obviously invalid or placeholder emails (e.g., "test@test", "example@example.com", "no-reply@", "admin@", "missing domain" etc.).
6. Do not attempt to verify whether the domain exists or is active — this is purely **syntactic and heuristic validation**.
7. An email belongs to the business if its domain clearly corresponds to the business name. You can use heuristics like:
   - Matching the main keywords of the business name to the domain (e.g., "mooserungolfcourse.com" for "Moose Run Golf Course").
   - Common abbreviations or variations of the business name in the domain are acceptable.

Formatting Requirements:
- Output only the valid emails that match the business.
- Maintain the same format as the input (e.g., JSON list).
- Do not include explanations or commentary unless explicitly requested.
- DO NOT INCLUDE ANY OTHER ADDITIONAL SPACES, CHARACTERS such as colon, spaces

Examples:

**Input:**
Business Name: "Moose Run Golf Course"  
Emails: ["info@mooserungolfcourse.com", "user@example.com", "tournaments@mooserungolfcourse.com", "admin@gmail.com"]

**Output:**
["info@mooserungolfcourse.com", "tournaments@mooserungolfcourse.com"]

---

If youa are unsure if the email belongs to the user or not just return valid emails
Your goal is to return a clean, trustworthy list of syntactically valid emails that are relevant to the specified business.
"""

load_dotenv()


def filter_emails(bussiness_name:str, emails: list[str]) -> list[str]: 
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
      "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
      "Content-Type": "application/json"
    }
    payload = {
      "model": "deepseek/deepseek-v3.2-exp",
      "messages": [
        {
          "role": "system",
          "content": f"{SYSTEM_PROMPT}"
        },
        {
          "role": "user",
          "content": f"""
                Business Name: {bussiness_name}
                Emails: {str(emails)}
          """
        }
      ],
      "reasoning": {
        "exclude": True
      }
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    res_json = response.json()

    choices = res_json.get("choices", [])
    if choices and "message" in choices[0]:
        content = choices[0]["message"].get("content", "[]")
    else:
        content = "[]"
    content = content.replace("'", '"')
    content = re.findall(r'"(.*?)"', content)
    return content
