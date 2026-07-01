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


@pytest.mark.asyncio
async def test_create_test_case_returns_201(db_session, auth_token, test_story):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/stories/{test_story.jira_id}/test-cases",
            json={
                "title": "Test checkout flow",
                "type": "functional",
                "steps": ["Add item to cart", "Proceed to checkout"],
                "expected_result": "Order is placed",
                "priority": "high",
                "source": "ai_generated",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test checkout flow"
    assert data["type"] == "functional"


@pytest.mark.asyncio
async def test_create_test_case_unknown_story_returns_404(db_session, auth_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/stories/UNKNOWN-999/test-cases",
            json={
                "title": "Some test",
                "type": "functional",
                "steps": ["step"],
                "expected_result": "result",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_sprint_release_score_returns_score(auth_token):
    from unittest.mock import AsyncMock, patch
    mock_score = {"score": 85, "recommendation": "go", "findings": ["Good coverage"]}
    with patch("app.agents.manual_qa.ManualQAAgent.score_release_readiness", new_callable=AsyncMock) as mock_score_fn:
        mock_score_fn.return_value = mock_score
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/sprints/SPRINT-1/release-score",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 85
    assert data["recommendation"] == "go"
