import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum, JSON
from app.models.base import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id = Column(String, ForeignKey("stories.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    type = Column(SAEnum(
        "functional", "edge", "negative", "security", "e2e", "performance",
        name="test_case_type"
    ), nullable=False)
    steps = Column(JSON, default=list)
    expected_result = Column(Text)
    priority = Column(SAEnum("high", "medium", "low", name="priority_level"), default="medium")
    source = Column(SAEnum("manual", "ai_generated", name="test_case_source"), default="ai_generated")
    created_by_agent = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
