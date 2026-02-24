"""
Memory manager — loads context and handles summarization.
"""
import os
from ollama_client import chat

CONTEXT_MESSAGES = int(os.getenv("CONTEXT_MESSAGES", 20))
SUMMARIZE_THRESHOLD = int(os.getenv("SUMMARIZE_THRESHOLD", 20))

SUMMARIZER_PROMPT = """You are a concise summarizer. Summarize the following chat history into
2-4 bullet points capturing the key facts and actions taken. Be brief."""


def build_context(conversation, messages: list) -> list[dict]:
    """
    Build the message list to send to the model for response generation.
    Includes summary (if exists) + last N messages.
    """
    context = []

    if conversation.summary:
        context.append({
            "role": "system",
            "content": f"Previous conversation summary:\n{conversation.summary}",
        })

    for msg in messages[-CONTEXT_MESSAGES:]:
        context.append({"role": msg.role, "content": msg.content})

    return context


def maybe_summarize(conversation, messages: list, db_session) -> None:
    """
    If message count exceeds threshold, summarize older messages
    and store in conversation.summary.
    """
    if len(messages) < SUMMARIZE_THRESHOLD:
        return

    # Only summarize messages older than the last 10
    to_summarize = messages[:-10]
    if not to_summarize:
        return

    history_text = "\n".join(
        f"{m.role.upper()}: {m.content[:300]}" for m in to_summarize
    )

    prompt = [
        {"role": "system", "content": SUMMARIZER_PROMPT},
        {"role": "user", "content": history_text},
    ]

    try:
        summary = chat(prompt, temperature=0.2)
        conversation.summary = summary
        db_session.commit()
    except Exception:
        pass  # Summarization is best-effort
