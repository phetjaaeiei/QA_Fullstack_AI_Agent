import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON
from app.models.base import Base


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, unique=True, nullable=False, index=True)
    project_id = Column(String)
    messages = Column(JSON, default=list)
    context = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
