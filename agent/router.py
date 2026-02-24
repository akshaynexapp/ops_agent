"""
Router — uses Ollama to parse user intent into a strict JSON tool action.
"""
import json
import re
from ollama_client import chat

ROUTER_SYSTEM_PROMPT = """You are an action router for a safe Ops Assistant. The user is non-technical.
You MUST output ONLY valid JSON and nothing else. No explanation, no markdown, no text before or after.

Choose exactly one action from:
get_disk_free, get_ram_usage, get_cpu_usage, get_uptime,
tail_nginx_error, tail_nginx_access,
list_workspace_files, create_text_file, read_text_file,
ask_clarification, refuse

Rules:
- Never output Linux commands.
- If user asks "nginx log" without specifying error or access: ask_clarification.
- For file creation: if user says "home", use workdir. Choose a safe filename from context.
- If content for file is missing: ask_clarification asking what to write inside.
- If user asks for delete/remove/stop/restart/kill/format/cleanup: output refuse.
- Never allow paths outside workdir. Never allow secrets, SSH keys, .env files.
- For nginx log questions, use lines=50 by default unless user specifies.

Output examples (JSON only):
{"action":"get_disk_free"}
{"action":"get_ram_usage"}
{"action":"get_cpu_usage"}
{"action":"get_uptime"}
{"action":"tail_nginx_error","lines":50}
{"action":"tail_nginx_access","lines":80}
{"action":"list_workspace_files"}
{"action":"create_text_file","filename":"note.txt","content":"hello world"}
{"action":"read_text_file","filename":"note.txt"}
{"action":"ask_clarification","question":"Do you want nginx error log or access log (visits)?"}
{"action":"refuse","reason":"Destructive actions are disabled for safety."}"""


def _fallback_action(text: str) -> dict | None:
    normalized = text.lower()
    tokens = set(re.findall(r"\b\w+\b", normalized))

    if "nginx" in normalized and "error" in normalized:
        return {"action": "tail_nginx_error", "lines": 50}
    if "nginx" in normalized and "access" in normalized:
        return {"action": "tail_nginx_access", "lines": 50}

    if "cpu" in tokens or "processor" in tokens:
        return {"action": "get_cpu_usage"}
    if "ram" in tokens or "memory" in tokens:
        return {"action": "get_ram_usage"}
    if "disk" in tokens or "storage" in tokens or "space" in tokens:
        return {"action": "get_disk_free"}
    if "uptime" in tokens or "running" in tokens:
        return {"action": "get_uptime"}

    if "workspace" in normalized and ("files" in tokens or "list" in tokens):
        return {"action": "list_workspace_files"}

    if "create" in tokens and "file" in tokens:
        return {"action": "ask_clarification", "question": "What should the new file be named and contain?"}
    if "read" in tokens and "file" in tokens:
        return {"action": "ask_clarification", "question": "Which workspace file should I read?"}

    return None


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from model output."""
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find JSON block
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Fallback
    return {"action": "ask_clarification", "question": "I didn't understand that. Could you rephrase?"}


def route(user_message: str, history: list[dict] | None = None) -> dict:
    """
    Given user message and optional history, return a tool action dict.
    history: list of {"role": "user"/"assistant", "content": "..."}
    """
    messages = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}]

    # Add recent history for context (last 6 turns)
    if history:
        for h in history[-6:]:
            if h["role"] in ("user", "assistant"):
                messages.append({"role": h["role"], "content": h["content"]})

    messages.append({"role": "user", "content": user_message})

    fallback = _fallback_action(user_message)
    if fallback:
        return fallback

    raw = chat(messages, temperature=0.0)
    return _extract_json(raw)
