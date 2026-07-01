from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.agents.orchestrator import QAOrchestrator
from app.database import get_db
from app.models.project import Project
from app.models.story import Story
from app.models.test_case import TestCase
from app.models.automation_script import AutomationScript

router = APIRouter()
orchestrator = QAOrchestrator()


def verify_ws_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


async def _get_or_create_story(db: AsyncSession, jira_id: str) -> Story:
    project_key = jira_id.split("-")[0]
    proj_res = await db.execute(select(Project).where(Project.jira_project_key == project_key))
    project = proj_res.scalar_one_or_none()
    if not project:
        project = Project(name=f"Project {project_key}", jira_project_key=project_key)
        db.add(project)
        await db.flush()

    story_res = await db.execute(select(Story).where(Story.jira_id == jira_id))
    story = story_res.scalar_one_or_none()
    if not story:
        story = Story(
            project_id=project.id,
            jira_id=jira_id,
            title=f"Story {jira_id}",
            description="",
            status="Unknown",
        )
        db.add(story)
        await db.flush()
    return story


async def _persist_test_cases(
    db: AsyncSession,
    jira_id: str,
    test_cases: list,
) -> None:
    story = await _get_or_create_story(db, jira_id)

    for tc_data in test_cases:
        tc = TestCase(
            story_id=story.id,
            title=tc_data.get("title", ""),
            type=tc_data.get("type", "functional"),
            steps=tc_data.get("steps", []),
            expected_result=tc_data.get("expected_result", ""),
            priority=tc_data.get("priority", "medium"),
            source="ai_generated",
            created_by_agent="manual_qa",
        )
        db.add(tc)
    await db.commit()


async def _persist_automation_script(
    db: AsyncSession,
    jira_id: str,
    script: dict,
) -> None:
    story = await _get_or_create_story(db, jira_id)

    automation_script = AutomationScript(
        story_id=story.id,
        framework=script.get("framework", "playwright"),
        content=script.get("content", ""),
        health_status="healthy",
    )
    db.add(automation_script)
    await db.commit()


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    email = verify_ws_token(token)
    if not email:
        await websocket.accept()
        await websocket.close(code=4001)
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") != "user_message":
                continue

            content = data.get("content", "")
            project_id = data.get("project_id", "")

            try:
                async for event in orchestrator.process(content, session_id, project_id):
                    if event.get("type") == "orchestrator_done":
                        ev_data = event.get("data") or {}
                        if ev_data.get("test_cases") and ev_data.get("story_id"):
                            await _persist_test_cases(db, ev_data["story_id"], ev_data["test_cases"])
                        if ev_data.get("script") and ev_data.get("story_id"):
                            await _persist_automation_script(db, ev_data["story_id"], ev_data["script"])
                    await websocket.send_json(event)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        pass
