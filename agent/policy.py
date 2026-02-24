"""
Safety policy layer — validates tool decisions before execution.
"""

DESTRUCTIVE_KEYWORDS = [
    "delete", "remove", "rm", "drop", "wipe", "format",
    "stop", "restart", "reboot", "shutdown", "kill", "pkill",
    "clean", "purge", "uninstall",
]

FORBIDDEN_PATHS = [
    "~/.ssh", "/etc/shadow", ".env", "id_rsa", "id_ed25519",
    "/root", "/etc/passwd", "authorized_keys", "known_hosts",
]

ALLOWED_TOOLS = {
    "get_disk_free",
    "get_ram_usage",
    "get_cpu_usage",
    "get_uptime",
    "tail_nginx_error",
    "tail_nginx_access",
    "list_workspace_files",
    "create_text_file",
    "read_text_file",
    "ask_clarification",
    "refuse",
}


class PolicyViolation(Exception):
    pass


def check(action: dict, user_message: str = "") -> dict:
    """
    Validate the action dict from the router.
    Returns the action unchanged if safe, raises PolicyViolation otherwise.
    """
    tool = action.get("action", "")

    # Unknown tool
    if tool not in ALLOWED_TOOLS:
        return {
            "action": "refuse",
            "reason": f"Tool '{tool}' is not available. I can only use approved tools.",
        }

    # Check user message for destructive intent
    msg_lower = user_message.lower()
    if any(kw in msg_lower for kw in DESTRUCTIVE_KEYWORDS) and tool not in ("ask_clarification", "refuse"):
        return {
            "action": "refuse",
            "reason": "Destructive actions (delete, stop, restart, remove, etc.) are disabled for safety.",
        }

    # Check for forbidden path access in file tools
    if tool in ("create_text_file", "read_text_file"):
        filename = action.get("filename", "")
        for forbidden in FORBIDDEN_PATHS:
            if forbidden in filename or ".." in filename or filename.startswith("/"):
                return {
                    "action": "refuse",
                    "reason": "Access to that path is not allowed for security reasons.",
                }

    # Check lines parameter bounds
    if tool in ("tail_nginx_error", "tail_nginx_access"):
        lines = action.get("lines", 50)
        if not isinstance(lines, int) or lines < 1:
            action["lines"] = 20
        elif lines > 200:
            action["lines"] = 200

    return action
