import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Integer
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


class ApiKey(Base):
    """API key per accesso programmatico a Genesi (B2B / integrations)."""
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)   # owner
    key_hash = Column(String, nullable=False, unique=True) # sha256 hex
    name = Column(String, nullable=True)                   # etichetta leggibile
    is_active = Column(Boolean, default=True)
    rate_limit_per_min = Column(Integer, default=30)       # max req/minuto
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    requests_total = Column(Integer, default=0)
