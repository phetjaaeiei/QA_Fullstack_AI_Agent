import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from app.models.base import Base


class Story(Base):
    __tablename__ = "stories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    jira_id = Column(String, nullable=False, index=True)
    title = Column(String)
    description = Column(Text)
    acceptance_criteria = Column(Text)
    status = Column(String)
    sprint_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
