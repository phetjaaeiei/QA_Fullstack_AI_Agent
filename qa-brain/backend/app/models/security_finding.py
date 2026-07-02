import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum
from app.models.base import Base


class SecurityFinding(Base):
    __tablename__ = "security_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id = Column(String, ForeignKey("stories.id"), nullable=False, index=True)
    owasp_category = Column(String, nullable=False)
    status = Column(SAEnum("covered", "gap", "not_applicable", name="security_finding_status"), nullable=False)
    risk_level = Column(SAEnum("critical", "high", "medium", "low", name="security_risk_level"), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
