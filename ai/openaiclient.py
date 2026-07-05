import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
# Allow overriding the model via env; fallback to a broadly available model
MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

if not API_KEY:
    client = None
else:
    client = OpenAI(api_key=API_KEY)

SYSTEM_PROMPT = """
You are Ayra, a smart, friendly female AI assistant.

Keep replies natural.
Keep replies under 120 words unless asked.
Help with coding, AI, Python, web development, and productivity.
Always be polite and encouraging.
"""

def ask_ai(prompt):
    """Send `prompt` to OpenAI and return assistant text.

    Raises RuntimeError with helpful messages on misconfiguration or API errors.
    """

    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY not found. Set it in .env or environment.")

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )

        # Handle expected response shapes from SDK
        try:
            return response.choices[0].message.content
        except Exception:
            try:
                return response["choices"][0]["message"]["content"]
            except Exception:
                return str(response)

    except Exception as e:
        # Wrap the underlying exception to make UI output clearer
        raise RuntimeError(f"OpenAI API error: {e}")