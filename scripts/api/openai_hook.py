# scripts/api/openai_hook.py

import os
import openai
from typing import List

# Load API key from environment or config
openai.api_key = os.getenv("OPENAI_API_KEY")

DEFAULT_MODEL = "gpt-4"


def call_openai(prompt: str, model: str = DEFAULT_MODEL, temperature: float = 0.7, max_tokens: int = 1000) -> str:
    """
    Makes a call to the OpenAI API using the specified model and returns the assistant response text.
    """
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[OpenAI Hook] API call failed: {e}")
        return "[ERROR: OpenAI API call failed]"


# Optional: Multi-prompt support
def call_openai_with_messages(messages: List[dict], model: str = DEFAULT_MODEL, temperature: float = 0.7, max_tokens: int = 1000) -> str:
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[OpenAI Hook] Multi-message API call failed: {e}")
        return "[ERROR: OpenAI API call failed]"