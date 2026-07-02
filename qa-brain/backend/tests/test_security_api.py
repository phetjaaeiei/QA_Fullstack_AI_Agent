import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.security_finding import SecurityFinding


@pytest.mark.asyncio
async def test_get_story_security_findings_returns_list(db_session, auth_token, test_story):
    finding = SecurityFinding(
        story_id=test_story.id,
        owasp_category="A01:2021-Broken Access Control",
        status="gap",
        risk_level="high",
        notes="No authorization check found",
    )
    db_session.add(finding)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/stories/{test_story.jira_id}/security-findings",
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["owasp_category"] == "A01:2021-Broken Access Control"
    assert data[0]["status"] == "gap"


@pytest.mark.asyncio
async def test_get_story_security_findings_unknown_story_returns_404(db_session, auth_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/stories/UNKNOWN-999/security-findings",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
    assert response.status_code == 404
