from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.story import Story
from app.models.test_case import TestCase

router = APIRouter(prefix="/api", tags=["test-cases"])


class TestCaseCreate(BaseModel):
    title: str
    type: str
    steps: List[str]
    expected_result: str
    priority: str = "medium"
    source: str = "ai_generated"


@router.get("/stories/{jira_id}/test-cases")
async def get_story_test_cases(
    jira_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    story_result = await db.execute(select(Story).where(Story.jira_id == jira_id))
    story = story_result.scalar_one_or_none()
    if not story:
        return []

    result = await db.execute(select(TestCase).where(TestCase.story_id == story.id))
    test_cases = result.scalars().all()
    return [
        {
            "id": tc.id,
            "story_id": tc.story_id,
            "title": tc.title,
            "type": tc.type,
            "steps": tc.steps,
            "expected_result": tc.expected_result,
            "priority": tc.priority,
            "source": tc.source,
            "created_at": tc.created_at.isoformat() if tc.created_at else None,
        }
        for tc in test_cases
    ]


@router.post("/stories/{jira_id}/test-cases", status_code=201)
async def create_test_case(
    jira_id: str,
    payload: TestCaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    story_result = await db.execute(select(Story).where(Story.jira_id == jira_id))
    story = story_result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail=f"Story {jira_id} not found")

    tc = TestCase(
        story_id=story.id,
        title=payload.title,
        type=payload.type,
        steps=payload.steps,
        expected_result=payload.expected_result,
        priority=payload.priority,
        source=payload.source,
        created_by_agent="manual_qa",
    )
    db.add(tc)
    await db.commit()
    await db.refresh(tc)
    return {"id": tc.id, "title": tc.title, "type": tc.type}
