from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from db import db
import uuid


INDIA_TZ = ZoneInfo("Asia/Kolkata")


def _ensure_utc(dt: datetime):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _format_indian_time(dt: datetime):
    ts = _ensure_utc(dt)
    if ts is None:
        return None
    return ts.astimezone(INDIA_TZ).isoformat()


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), default="New Chat")
    summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    messages = db.relationship("Message", backref="conversation", lazy=True, cascade="all, delete-orphan")
    tool_runs = db.relationship("ToolRun", backref="conversation", lazy=True, cascade="all, delete-orphan")
    user = db.relationship("User", back_populates="conversations")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "created_at": _format_indian_time(self.created_at),
            "updated_at": _format_indian_time(self.updated_at),
            "user_id": self.user_id,
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user / assistant / system
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": _format_indian_time(self.created_at),
        }


class ToolRun(db.Model):
    __tablename__ = "tool_runs"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=True)
    tool_name = db.Column(db.String(100), nullable=False)
    input_json = db.Column(db.Text, nullable=True)
    output_text = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="ok")  # ok / error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    auth_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    conversations = db.relationship("Conversation", back_populates="user", lazy=True)

    def set_password(self, password: str) -> None:
        from werkzeug.security import generate_password_hash

        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash

        return check_password_hash(self.password_hash, password)

    def refresh_token(self) -> str:
        self.auth_token = uuid.uuid4().hex
        return self.auth_token
