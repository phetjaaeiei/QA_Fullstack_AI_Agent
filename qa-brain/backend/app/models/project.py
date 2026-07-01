import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from app.models.base import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    jira_project_key = Column(String)
    github_repo = Column(String)
    figma_file_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
