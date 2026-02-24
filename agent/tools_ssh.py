"""
SSH tool runner — all commands run on the remote PC via paramiko.
Only allowlisted, safe commands are executed.
"""
import os
import json
import posixpath
import paramiko
from dotenv import load_dotenv

load_dotenv()

SSH_HOST = os.getenv("SSH_HOST", "192.168.10.56")
SSH_USER = os.getenv("SSH_USER", "nexapp-server")
SSH_PORT = int(os.getenv("SSH_PORT", 22))
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "/home/nexapp-server/.ssh/id_ed25519")
SSH_WORKDIR = os.getenv("SSH_WORKDIR", "/home/nexapp-server/ops_workspace")


def _get_client() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=SSH_HOST,
        port=SSH_PORT,
        username=SSH_USER,
        key_filename=SSH_KEY_PATH,
        timeout=15,
    )
    return client


def _run(cmd: str) -> tuple[str, str, int]:
    """Run a command on the remote PC. Returns (stdout, stderr, exit_code)."""
    client = _get_client()
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        code = stdout.channel.recv_exit_status()
        return out, err, code
    finally:
        client.close()


def _safe_workdir_path(filename: str) -> str:
    """Ensure filename resolves inside workdir. Raises ValueError if not."""
    # Strip any leading slashes or directory traversal
    safe_name = posixpath.basename(filename.replace("..", ""))
    if not safe_name:
        raise ValueError("Invalid filename.")
    return posixpath.join(SSH_WORKDIR, safe_name)


# ─── Tool implementations ──────────────────────────────────────────────────────

def get_disk_free() -> str:
    out, err, code = _run("df -h / | tail -1")
    if code != 0:
        return f"Error: {err}"
    parts = out.split()
    if len(parts) >= 5:
        return (
            f"Filesystem: {parts[0]}\n"
            f"Total: {parts[1]}  Used: {parts[2]}  Free: {parts[3]}  Use%: {parts[4]}"
        )
    return out


def get_ram_usage() -> str:
    out, err, code = _run("free -h")
    if code != 0:
        return f"Error: {err}"
    return out


def get_cpu_usage() -> str:
    out, err, code = _run(
        "top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4\"%\"}' || "
        "cat /proc/loadavg"
    )
    if code != 0:
        return f"Error: {err}"
    return out or "Unable to read CPU usage."


def get_uptime() -> str:
    out, err, code = _run("uptime -p && uptime")
    if code != 0:
        out, err, code = _run("uptime")
    return out if out else f"Error: {err}"


def tail_nginx_error(lines: int = 50) -> str:
    lines = max(20, min(lines, 200))
    log_path = "/var/log/nginx/error.log"
    out, err, code = _run(f"tail -n {lines} {log_path} 2>&1")
    if "Permission denied" in out or "Permission denied" in err or code == 1:
        return (
            "⚠️ I can't read the nginx error log due to file permissions.\n"
            "To fix this, the server admin can run:\n"
            "  `sudo usermod -aG adm nexapp-server`\n"
            "Then log out and back in."
        )
    return out if out else "Nginx error log is empty."


def tail_nginx_access(lines: int = 50) -> str:
    lines = max(20, min(lines, 200))
    log_path = "/var/log/nginx/access.log"
    out, err, code = _run(f"tail -n {lines} {log_path} 2>&1")
    if "Permission denied" in out or "Permission denied" in err or code == 1:
        return (
            "⚠️ I can't read the nginx access log due to file permissions.\n"
            "To fix this, the server admin can run:\n"
            "  `sudo usermod -aG adm nexapp-server`\n"
            "Then log out and back in."
        )
    return out if out else "Nginx access log is empty."


def list_workspace_files() -> str:
    out, err, code = _run(f"ls -lh {SSH_WORKDIR} 2>&1")
    if code != 0:
        return f"Error listing workspace: {err}"
    return out if out else "Workspace is empty."


def create_text_file(filename: str, content: str) -> str:
    try:
        path = _safe_workdir_path(filename)
    except ValueError as e:
        return f"Error: {e}"

    # Use SFTP to write file safely (no shell injection risk)
    client = _get_client()
    try:
        sftp = client.open_sftp()
        # Ensure workdir exists
        try:
            sftp.stat(SSH_WORKDIR)
        except FileNotFoundError:
            sftp.mkdir(SSH_WORKDIR)

        with sftp.open(path, "w") as f:
            f.write(content)
        sftp.close()
        return f"File '{filename}' created successfully in workspace."
    except Exception as e:
        return f"Error creating file: {e}"
    finally:
        client.close()


def read_text_file(filename: str) -> str:
    try:
        path = _safe_workdir_path(filename)
    except ValueError as e:
        return f"Error: {e}"

    client = _get_client()
    try:
        sftp = client.open_sftp()
        with sftp.open(path, "r") as f:
            content = f.read().decode("utf-8", errors="replace")
        sftp.close()
        return content if content else "(File is empty)"
    except FileNotFoundError:
        return f"File '{filename}' not found in workspace."
    except Exception as e:
        return f"Error reading file: {e}"
    finally:
        client.close()


# ─── Dispatcher ───────────────────────────────────────────────────────────────

TOOL_MAP = {
    "get_disk_free": lambda a: get_disk_free(),
    "get_ram_usage": lambda a: get_ram_usage(),
    "get_cpu_usage": lambda a: get_cpu_usage(),
    "get_uptime": lambda a: get_uptime(),
    "tail_nginx_error": lambda a: tail_nginx_error(a.get("lines", 50)),
    "tail_nginx_access": lambda a: tail_nginx_access(a.get("lines", 50)),
    "list_workspace_files": lambda a: list_workspace_files(),
    "create_text_file": lambda a: create_text_file(a.get("filename", "note.txt"), a.get("content", "")),
    "read_text_file": lambda a: read_text_file(a.get("filename", "")),
}


def run_tool(action: dict) -> str:
    """Dispatch action to the correct tool function."""
    tool_name = action.get("action")
    fn = TOOL_MAP.get(tool_name)
    if fn is None:
        return f"Unknown tool: {tool_name}"
    try:
        return fn(action)
    except Exception as e:
        return f"Tool error ({tool_name}): {e}"
