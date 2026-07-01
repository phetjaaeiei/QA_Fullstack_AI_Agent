import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum as SAEnum
from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum("qa_engineer", "qa_lead", "admin", name="user_role"), default="qa_engineer")
    created_at = Column(DateTime, default=datetime.utcnow)
