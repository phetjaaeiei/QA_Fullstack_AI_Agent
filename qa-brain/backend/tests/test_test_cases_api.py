import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.test_case import TestCase


@pytest.mark.asyncio
async def test_get_story_test_cases_returns_list(db_session, auth_token, test_story):
    tc = TestCase(
        story_id=test_story.id,
        title="Test login",
        type="functional",
        steps=["Open login page", "Enter credentials"],
        expected_result="User is logged in",
        priority="high",
        source="ai_generated",
    )
    db_session.add(tc)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/stories/{test_story.jira_id}/test-cases",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["title"] == "Test login"
