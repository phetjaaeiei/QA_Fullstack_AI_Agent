import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.automation_script import AutomationScript


@pytest.mark.asyncio
async def test_get_story_scripts_returns_list(db_session, auth_token, test_story):
    script = AutomationScript(
        story_id=test_story.id,
        framework="playwright",
        content="test('x', async () => {});",
        health_status="healthy",
    )
    db_session.add(script)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/stories/{test_story.jira_id}/scripts",
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["framework"] == "playwright"


@pytest.mark.asyncio
async def test_get_story_scripts_unknown_story_returns_404(db_session, auth_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stories/UNKNOWN-999/scripts",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
    assert response.status_code == 404
