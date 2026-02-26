import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class AuthUser(Base):
    __tablename__ = "auth_users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    preferences = Column(JSON, default=lambda: {
        "language": "it",
        "timezone": "Europe/Rome",
        "style_preference": "relazionale",
        "main_goal": "",
        "age_range": "",
    })


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    token_type = Column(String, nullable=False)  # "verify_email" | "reset_password"
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)


class Visit(Base):
    __tablename__ = "visits"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    path = Column(String, default="/")
    visited_at = Column(DateTime, default=datetime.utcnow)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    model = Column(String, nullable=False)
    prompt_tokens = Column(JSON, default=0) # Storing as total count for now
    completion_tokens = Column(JSON, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
