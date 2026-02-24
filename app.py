import os
import uuid
import json
from datetime import datetime, timezone

from flask import (
    Flask, render_template, request, jsonify,
    session, Response, stream_with_context
)
from dotenv import load_dotenv

load_dotenv()

from db import db, init_db
from models import Conversation, Message, ToolRun, User
from ollama_client import generate_title
from agent.router import route
from agent.policy import check
from agent.tools_ssh import run_tool
from agent.formatters import format_tool_result, format_clarification, format_refusal
from agent.memory import build_context, maybe_summarize

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
os.makedirs(os.path.dirname(os.getenv("DATABASE_URL", "instance/ops_agent.db")), exist_ok=True)
INSTANCE_DIR = os.path.join(os.path.dirname(__file__), "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
default_db = f"sqlite:///{os.path.join(INSTANCE_DIR, 'ops_agent.db')}"
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", default_db)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

init_db(app)

SESSION_HEADER = "X-Session-Id"
USER_HEADER = "X-User-Token"


def get_session_id():
    sid = request.headers.get(SESSION_HEADER)
    if sid:
        session["session_id"] = sid
        return sid
    sid = session.get("session_id")
    if not sid:
        sid = str(uuid.uuid4())
        session["session_id"] = sid
    return sid


def json_response(payload, status=200, sid=None, user_token=None):
    sid = sid or get_session_id()
    response = jsonify(payload)
    response.status_code = status
    response.headers[SESSION_HEADER] = sid
    if user_token:
        response.headers[USER_HEADER] = user_token
    return response


def get_user_from_token():
    token = request.headers.get(USER_HEADER)
    if not token:
        return None
    return User.query.filter_by(auth_token=token).first()


def authenticate_user():
    sid = get_session_id()
    user = get_user_from_token()
    if not user:
        return None, json_response({"error": "Authentication required"}, status=401, sid=sid)
    return user, None


@app.route("/api/register", methods=["POST"])
def register():
    sid = get_session_id()
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")
    confirm = data.get("confirm_password", "")

    if not email or not password:
        return json_response({"error": "Email and password are required."}, status=400, sid=sid)
    if password != confirm:
        return json_response({"error": "Passwords do not match."}, status=400, sid=sid)
    if len(password) < 8:
        return json_response({"error": "Password must be at least 8 characters."}, status=400, sid=sid)
    if User.query.filter_by(email=email).first():
        return json_response({"error": "Email already registered."}, status=400, sid=sid)

    user = User(email=email, auth_token=uuid.uuid4().hex)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return json_response({"message": "Registration successful."}, sid=sid, user_token=user.auth_token)


@app.route("/api/login", methods=["POST"])
def login():
    sid = get_session_id()
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return json_response({"error": "Email and password are required."}, status=400, sid=sid)

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return json_response({"error": "Invalid email or password."}, status=401, sid=sid)

    user.refresh_token()
    db.session.commit()
    return json_response({"message": "Login successful."}, sid=sid, user_token=user.auth_token)


@app.route("/api/logout", methods=["POST"])
def logout():
    sid = get_session_id()
    user = get_user_from_token()
    if not user:
        return json_response({"error": "Authentication required."}, status=401, sid=sid)
    user.refresh_token()
    db.session.commit()
    return json_response({"message": "Logged out."}, sid=sid)


@app.route("/api/me", methods=["GET"])
def get_current_user():
    sid = get_session_id()
    user, err = authenticate_user()
    if err:
        return err
    return json_response({"email": user.email}, sid=sid, user_token=user.auth_token)


# ─── UI ───────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    get_session_id()
    return render_template("index.html")


@app.route("/api/conversations", methods=["GET"])
def list_conversations():
    sid = get_session_id()
    user, err = authenticate_user()
    if err:
        return err
    convs = (
        Conversation.query
        .filter_by(user_id=user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return json_response([c.to_dict() for c in convs], sid=sid, user_token=user.auth_token)


@app.route("/api/conversations", methods=["POST"])
def create_conversation():
    sid = get_session_id()
    user, err = authenticate_user()
    if err:
        return err
    conv = Conversation(session_id=sid, title="New Chat", user_id=user.id)
    db.session.add(conv)
    db.session.commit()
    return json_response(conv.to_dict(), status=201, sid=sid, user_token=user.auth_token)


@app.route("/api/conversations/<int:conv_id>/messages", methods=["GET"])
def get_messages(conv_id):
    sid = get_session_id()
    user, err = authenticate_user()
    if err:
        return err
    conv = Conversation.query.filter_by(id=conv_id, user_id=user.id).first()
    if not conv:
        return json_response({"error": "Conversation not found"}, status=404, sid=sid, user_token=user.auth_token)
    msgs = Message.query.filter_by(conversation_id=conv.id).order_by(Message.created_at).all()
    return json_response([m.to_dict() for m in msgs], sid=sid, user_token=user.auth_token)


@app.route("/api/conversations/<int:conv_id>/rename", methods=["POST"])
def rename_conversation(conv_id):
    sid = get_session_id()
    user, err = authenticate_user()
    if err:
        return err
    conv = Conversation.query.filter_by(id=conv_id, user_id=user.id).first()
    if not conv:
        return json_response({"error": "Conversation not found"}, status=404, sid=sid, user_token=user.auth_token)
    data = request.get_json()
    conv.title = data.get("title", conv.title)[:200]
    db.session.commit()
    return json_response(conv.to_dict(), sid=sid, user_token=user.auth_token)


@app.route("/api/conversations/<int:conv_id>", methods=["DELETE"])
def delete_conversation(conv_id):
    sid = get_session_id()
    user, err = authenticate_user()
    if err:
        return err
    conv = Conversation.query.filter_by(id=conv_id, user_id=user.id).first()
    if not conv:
        return json_response({"error": "Conversation not found"}, status=404, sid=sid, user_token=user.auth_token)
    db.session.delete(conv)
    db.session.commit()
    return json_response({"deleted": True}, sid=sid, user_token=user.auth_token)


# ─── Chat ─────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    sid = get_session_id()
    data = request.get_json()
    user_message = (data.get("message") or "").strip()
    conv_id = data.get("conversation_id")
    user, err = authenticate_user()
    if err:
        return err
    user_token = user.auth_token

    if not user_message:
        return json_response({"error": "Empty message"}, status=400, sid=sid, user_token=user_token)

    if conv_id:
        conv = Conversation.query.filter_by(id=conv_id, user_id=user.id).first()
        if not conv:
            # Conversation may have been deleted or corrupted; start fresh
            conv = Conversation(session_id=sid, title="New Chat", user_id=user.id)
            db.session.add(conv)
            db.session.flush()
    else:
        conv = Conversation(session_id=sid, title="New Chat", user_id=user.id)
        db.session.add(conv)
        db.session.flush()

    # Save user message
    user_msg = Message(conversation_id=conv.id, role="user", content=user_message)
    db.session.add(user_msg)
    db.session.flush()
    user_msg_id = user_msg.id

    # Update title if first message
    if Message.query.filter_by(conversation_id=conv.id, role="user").count() == 1:
        try:
            conv.title = generate_title(user_message)
        except Exception:
            conv.title = user_message[:60]

    # Load message history for context
    all_messages = Message.query.filter_by(conversation_id=conv.id).order_by(Message.created_at).all()
    history = build_context(conv, all_messages)

    # Maybe summarize old messages and persist the conversation before the tool runs
    maybe_summarize(conv, all_messages, db.session)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    conv = db.session.merge(conv)
    conv_id = conv.id
    conv_title = conv.title

    def generate():
        assistant_msg_id = None
        assistant_created_at = None
        try:
            # Route the user message to a tool
            action = route(user_message, history)

            # Policy check
            action = check(action, user_message)

            tool_name = action.get("action")

            # Handle meta-actions
            if tool_name == "ask_clarification":
                response_text = format_clarification(action.get("question", "Could you clarify?"))
            elif tool_name == "refuse":
                response_text = format_refusal(action.get("reason", "This action is not allowed."))
            else:
                # Run the tool
                tool_output = run_tool(action)

                # Log tool run
                tool_run = ToolRun(
                    conversation_id=conv_id,
                    message_id=user_msg_id,
                    tool_name=tool_name,
                    input_json=json.dumps(action),
                    output_text=tool_output[:5000],
                    status="ok" if "Error" not in tool_output else "error",
                )
                db.session.add(tool_run)

                # Format response
                response_text = format_tool_result(tool_name, tool_output, user_message)

            # Save assistant message
            assistant_msg = Message(
                conversation_id=conv_id,
                role="assistant",
                content=response_text,
            )
            db.session.add(assistant_msg)
            db.session.flush()
            assistant_msg_id = assistant_msg.id
            assistant_created_at = assistant_msg.created_at
            Conversation.query.filter_by(id=conv_id).update({"updated_at": datetime.utcnow()})
            db.session.commit()

            # Stream response as SSE
            yield f"data: {json.dumps({'type': 'session', 'session_id': sid})}\n\n"
            yield f"data: {json.dumps({'type': 'conv_id', 'conv_id': conv_id, 'title': conv_title})}\n\n"

            # Stream text word by word for a smooth feel
            words = response_text.split(" ")
            chunk = ""
            for i, word in enumerate(words):
                chunk += word + " "
                if (i + 1) % 5 == 0 or i == len(words) - 1:
                    yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
                    chunk = ""

            yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg_id, 'created_at': assistant_created_at.isoformat()})}\n\n"

        except RuntimeError as e:
            error_msg = str(e)
            yield f"data: {json.dumps({'type': 'error', 'text': error_msg})}\n\n"
            # Save error as assistant message
            err_message = Message(
                conversation_id=conv_id,
                role="assistant",
                content=f"⚠️ {error_msg}",
            )
            db.session.add(err_message)
            db.session.commit()

    resp = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
    resp.headers[SESSION_HEADER] = sid
    resp.headers[USER_HEADER] = user_token
    return resp


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
