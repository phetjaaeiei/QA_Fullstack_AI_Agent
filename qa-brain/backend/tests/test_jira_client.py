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


MOCK_CREATE_ISSUE_RESPONSE = {
    "id": "10050",
    "key": "SCRUM-999",
    "self": "https://example.atlassian.net/rest/api/3/issue/10050",
}


@pytest.mark.asyncio
async def test_create_issue_returns_normalized_dict():
    client = JiraClient()
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_CREATE_ISSUE_RESPONSE
    mock_response.raise_for_status = lambda: None

    with patch.object(client._http, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await client.create_issue(
            project_key="SCRUM",
            summary="SQL injection in login form",
            description="The email field is vulnerable to SQL injection.",
            issue_type="Bug",
            labels=["security"],
        )

    assert result["jira_id"] == "SCRUM-999"
    # Mock base_url is from settings.jira_base_url; verify exact URL structure to catch double-slash regression
    expected_url = f"{str(client._http.base_url).rstrip('/')}/browse/SCRUM-999"
    assert result["url"] == expected_url

    call_kwargs = mock_post.call_args
    assert call_kwargs.args[0] == "/rest/api/3/issue"
    sent_fields = call_kwargs.kwargs["json"]["fields"]
    assert sent_fields["project"]["key"] == "SCRUM"
    assert sent_fields["summary"] == "SQL injection in login form"
    assert sent_fields["issuetype"]["name"] == "Bug"
    assert sent_fields["labels"] == ["security"]
    assert sent_fields["description"]["type"] == "doc"
    assert sent_fields["description"]["content"][0]["type"] == "paragraph"


@pytest.mark.asyncio
async def test_create_issue_defaults_issue_type_and_labels():
    client = JiraClient()
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_CREATE_ISSUE_RESPONSE
    mock_response.raise_for_status = lambda: None

    with patch.object(client._http, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        await client.create_issue(
            project_key="SCRUM",
            summary="XSS in comment field",
            description="Reflected XSS found in the comment textarea.",
        )

    sent_fields = mock_post.call_args.kwargs["json"]["fields"]
    assert sent_fields["issuetype"]["name"] == "Bug"
    assert sent_fields["labels"] == []
