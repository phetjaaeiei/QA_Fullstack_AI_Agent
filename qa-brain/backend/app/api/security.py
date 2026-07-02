from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.story import Story
from app.models.security_finding import SecurityFinding

router = APIRouter(prefix="/api", tags=["security"])


@router.get("/stories/{jira_id}/security-findings")
async def get_story_security_findings(
    jira_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    story_result = await db.execute(select(Story).where(Story.jira_id == jira_id))
    story = story_result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail=f"Story {jira_id} not found")

    result = await db.execute(select(SecurityFinding).where(SecurityFinding.story_id == story.id))
    findings = result.scalars().all()
    return [
        {
            "id": f.id,
            "story_id": f.story_id,
            "owasp_category": f.owasp_category,
            "status": f.status,
            "risk_level": f.risk_level,
            "notes": f.notes,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in findings
    ]
