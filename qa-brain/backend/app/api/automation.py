from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.story import Story
from app.models.automation_script import AutomationScript

router = APIRouter(prefix="/api", tags=["automation"])


@router.get("/stories/{jira_id}/scripts")
async def get_story_scripts(
    jira_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    story_result = await db.execute(select(Story).where(Story.jira_id == jira_id))
    story = story_result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail=f"Story {jira_id} not found")

    result = await db.execute(select(AutomationScript).where(AutomationScript.story_id == story.id))
    scripts = result.scalars().all()
    return [
        {
            "id": s.id,
            "story_id": s.story_id,
            "framework": s.framework,
            "content": s.content,
            "health_status": s.health_status,
            "ci_run_url": s.ci_run_url,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in scripts
    ]
