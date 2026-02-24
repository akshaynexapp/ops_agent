"""
Response formatter — turns raw tool output into friendly, readable answers.
"""
from ollama_client import chat

FORMATTER_SYSTEM_PROMPT = """You are a friendly Ops Assistant helping a non-technical user.
You are given raw output from a server tool. Your job is to:
1. Explain results in plain English, short and clear.
2. Show key numbers with proper units (GB, MB, %, etc.).
3. For nginx logs: briefly summarize what you see, highlight the last 3-5 relevant lines.
4. Never dump raw command output without explanation.
5. Be warm and helpful. Use bullet points or bold for clarity.
6. If there's an error or permission issue, explain it simply and suggest a fix.
7. Keep answers concise — no more than 150 words unless log analysis requires more."""


def format_tool_result(tool_name: str, tool_output: str, user_message: str) -> str:
    """Ask the LLM to turn raw tool output into a friendly response."""
    prompt = [
        {"role": "system", "content": FORMATTER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"The user asked: \"{user_message}\"\n\n"
                f"Tool used: {tool_name}\n"
                f"Raw output:\n{tool_output}\n\n"
                "Please write a friendly, clear response for this non-technical user."
            ),
        },
    ]
    try:
        return chat(prompt, temperature=0.3)
    except Exception as e:
        return f"Here's the raw result:\n\n```\n{tool_output}\n```"


def format_clarification(question: str) -> str:
    return question


def format_refusal(reason: str) -> str:
    return f"I'm sorry, I can't do that. {reason}\n\nI can help you with: checking disk, RAM, CPU, uptime, nginx logs, and managing files in the workspace."
