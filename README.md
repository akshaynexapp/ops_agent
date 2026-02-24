# Ops Agent — Server Assistant

A production-quality Flask application providing  natural-language server monitoring over SSH.

## Features

- 🤖 **AI-powered routing** — Ollama + qwen2.5-coder understands plain English
- 🔒 **Safe by design** — only allowlisted read-only tools, no arbitrary shell commands
- 📡 **SSH execution** — all commands run on remote PC via paramiko
- 🌊 **Streaming responses** — SSE-based word-by-word streaming
- 🗃️ **Persistent history** — SQLite + SQLAlchemy, with auto-summarization
- 📱 **Mobile responsive** — works on phones too

## Repo Structure

```
ops_agent/
├── app.py                  # Flask app, routes
├── db.py                   # SQLAlchemy setup
├── models.py               # Conversation, Message, ToolRun
├── ollama_client.py        # Ollama HTTP API client
├── agent/
│   ├── router.py           # JSON-only tool router (LLM)
│   ├── tools_ssh.py        # SSH tool executor (allowlisted)
│   ├── policy.py           # Safety policy layer
│   ├── formatters.py       # Friendly response formatter
│   └── memory.py           # Context + summarization
├── templates/
│   └── index.html          # Chat UI
├── static/
│   ├── styles.css          # Dark/light theme CSS
│   └── app.js              # Vanilla JS frontend
├── .env.example            # Config template
├── requirements.txt
└── README.md
```

## Setup & Run

### 1. Clone and install dependencies

```bash
cd ops_agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your SSH credentials and Ollama URL
nano .env
```

### 3. Ensure Ollama model is ready (on remote PC)

```bash
# On the remote PC (192.168.10.56):
ollama pull qwen2.5-coder:0.5b
```

### 4. Ensure SSH key access works

```bash
ssh -i /home/server/.ssh/id_***** server@192.168.10.* "echo ok"
```

### 5. Create workspace directory (on remote PC)

```bash
ssh server@192.168.10.* "mkdir -p /home/server/ops_workspace"
```

### 6. Run the app

```bash
python app.py
# Open http://localhost:5000
```

For production:
```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 --timeout 120 app:app
```

## Accounts & Conversation History

- **Register from the UI:** Click the login panel (shown automatically if you're not signed in), enter an email address, password, and confirm the password (passwords must match and be at least 8 characters). The app stores your auth token locally and keeps conversation history tied to that account.
- **Log in:** Use the same panel to sign back in with your registered email and password. You can also call `/api/login` with `email` and `password` in the JSON body for automation.
- **Token storage:** Tokens live in `localStorage` under `ops-agent-user-token` and `ops-agent-session-id`. Use the “Clear stored tokens” button in the UI or run `localStorage.removeItem('ops-agent-user-token')` and `localStorage.removeItem('ops-agent-session-id')` in the browser console if you need to reset.
- **Conversation history:** Once logged in, the left sidebar lists all chats saved to your user account. Closing the browser or opening the dashboard on another device uses the same account to show your previous conversations.
- **Profile & logout:** The header shows the active email once signed in, and you can tap the logout button to clear that session (the same button also refreshes the history in case you switch machines). Logging out re-opens the authentication modal so you can sign in again.
- **Persistent datastore:** The Flask app writes to `instance/ops_agent.db` by default (it auto-creates the `instance/` directory). If you want a different path, set `DATABASE_URL` before starting the server so authentication, conversations, and history all hit the same file.

## What Users Can Ask

| Plain English | Tool Used |
|---|---|
| "how much disk space is left?" | `get_disk_free` |
| "check ram usage" | `get_ram_usage` |
| "whats the cpu at" | `get_cpu_usage` |
| "how long has server been up" | `get_uptime` |
| "show nginx error log" | `tail_nginx_error` |
| "show nginx access log" | `tail_nginx_access` |
| "what files are in workspace" | `list_workspace_files` |
| "create a file called notes.txt with hello" | `create_text_file` |
| "read notes.txt" | `read_text_file` |

## Security

- All commands run over SSH with a restricted key
- No arbitrary shell execution — only allowlisted tools
- File operations locked to `/home/server/ops_workspace`
- Destructive actions (delete, stop, restart) are refused
- Forbidden paths (`.ssh`, `.env`, `/etc/shadow`) are blocked
- Policy layer validates all LLM decisions before execution

## Allowed Tools

`get_disk_free` · `get_ram_usage` · `get_cpu_usage` · `get_uptime` · `tail_nginx_error` · `tail_nginx_access` · `list_workspace_files` · `create_text_file` · `read_text_file` · `ask_clarification` · `refuse`
