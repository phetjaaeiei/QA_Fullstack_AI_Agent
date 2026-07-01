import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum
from app.models.base import Base


class AutomationScript(Base):
    __tablename__ = "automation_scripts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id = Column(String, ForeignKey("stories.id"), nullable=False, index=True)
    test_case_id = Column(String, ForeignKey("test_cases.id"), nullable=True)
    framework = Column(SAEnum("playwright", "robot", name="automation_framework"), nullable=False)
    content = Column(Text, nullable=False)
    health_status = Column(SAEnum("healthy", "flaky", "broken", name="script_health_status"), default="healthy")
    last_run_at = Column(DateTime, nullable=True)
    failure_root_cause = Column(String, nullable=True)
    ci_run_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
