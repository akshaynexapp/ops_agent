import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.10.56:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:0.5b")


def chat(messages: list, stream: bool = False, temperature: float = 0.1) -> str:
    """Send messages to Ollama and return the response text."""
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": temperature},
    }
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        if stream:
            full = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    full += chunk
                    if data.get("done"):
                        break
            return full
        else:
            return response.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Cannot connect to Ollama. Make sure Ollama is running at "
            f"{OLLAMA_BASE_URL} and the model '{OLLAMA_MODEL}' is pulled."
        )
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


def generate_title(user_message: str) -> str:
    """Generate a short conversation title from the first user message."""
    prompt = [
        {
            "role": "user",
            "content": (
                f"Create a short (3-5 words) title for a chat that starts with: '{user_message}'. "
                "Output ONLY the title, no quotes, no extra text."
            ),
        }
    ]
    try:
        title = chat(prompt, temperature=0.3).strip().strip('"').strip("'")
        return title[:100] if title else user_message[:60]
    except Exception:
        return user_message[:60]
