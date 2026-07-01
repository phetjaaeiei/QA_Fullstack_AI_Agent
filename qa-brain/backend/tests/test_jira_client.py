import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.mcp_clients.jira_client import JiraClient


MOCK_STORY_RESPONSE = {
    "id": "10001",
    "key": "PROJ-123",
    "fields": {
        "summary": "User can login with email and password",
        "description": {
            "content": [{"content": [{"text": "As a user I want to login", "type": "text"}], "type": "paragraph"}]
        },
        "acceptance_criteria": "Given valid credentials, user is logged in",
        "status": {"name": "In Progress"},
    }
}


@pytest.mark.asyncio
async def test_get_story_returns_normalized_dict():
    client = JiraClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_STORY_RESPONSE
    mock_response.raise_for_status = lambda: None

    with patch.object(client._http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        story = await client.get_story("PROJ-123")

    assert story["jira_id"] == "PROJ-123"
    assert story["title"] == "User can login with email and password"
    assert "description" in story
    assert "acceptance_criteria" in story


@pytest.mark.asyncio
async def test_get_story_raises_on_404():
    client = JiraClient()
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = Exception("404 Not Found")

    with patch.object(client._http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="404"):
            await client.get_story("PROJ-999")
