import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.security_qa import SecurityQAAgent

MOCK_STORY = {
    "jira_id": "SCRUM-300",
    "title": "User can upload a profile picture",
    "description": "As a user I want to upload a profile picture so my account feels personal",
    "acceptance_criteria": "Given an image file under 5MB, when I upload it, then it becomes my avatar",
    "status": "In Progress",
}

MOCK_OWASP_TEST_CASES = [
    {
        "title": "Reject oversized file upload",
        "type": "security",
        "owasp_category": "A04:2021-Insecure Design",
        "steps": ["Step 1: Attempt to upload a 50MB file", "Step 2: Submit"],
        "expected_result": "Upload is rejected with a clear size-limit error",
        "priority": "high",
    },
]

MOCK_OWASP_MAPPING = [
    {
        "owasp_category": "A01:2021-Broken Access Control",
        "status": "gap",
        "risk_level": "high",
        "notes": "No check that the uploader owns the profile being modified",
    },
    {
        "owasp_category": "A04:2021-Insecure Design",
        "status": "covered",
        "risk_level": "medium",
        "notes": "File size and type are validated before upload",
    },
]

MOCK_RBAC_MATRIX = {
    "roles": ["admin", "member", "guest"],
    "matrix": [
        {
            "boundary": "Delete another user's project",
            "access": {"admin": "allow", "member": "deny", "guest": "deny"},
        },
        {
            "boundary": "View own project settings",
            "access": {"admin": "allow", "member": "allow", "guest": "deny"},
        },
    ],
}

SAMPLE_OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Sample API", "version": "1.0.0"},
    "paths": {
        "/users/{id}": {
            "get": {"summary": "Get user", "parameters": [{"name": "id", "in": "path"}], "responses": {"200": {"description": "OK"}}},
            "delete": {"summary": "Delete user", "parameters": [{"name": "id", "in": "path"}], "responses": {"204": {"description": "No Content"}}},
        }
    },
}

MOCK_API_SECURITY_CHECKLIST = {
    "broken_access": ["Verify /users/{id} DELETE checks the caller owns or administers the target user"],
    "injection": ["Verify {id} path parameter is validated as a UUID/int before use in queries"],
    "auth": ["Verify /users/{id} endpoints require an authenticated session"],
}


@pytest.mark.asyncio
async def test_generate_owasp_test_cases_returns_list():
    with patch("app.agents.security_qa.settings.mock_mode", False):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_OWASP_TEST_CASES))]
            )
            result = await agent.generate_owasp_test_cases("SCRUM-300")

    assert len(result) == 1
    assert result[0]["owasp_category"] == "A04:2021-Insecure Design"
    assert result[0]["type"] == "security"


@pytest.mark.asyncio
async def test_generate_owasp_test_cases_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_mode", True):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.generate_owasp_test_cases("SCRUM-300")

    assert len(result) >= 1
    assert result[0]["title"].startswith("[MOCK]")
    assert result[0]["type"] == "security"


@pytest.mark.asyncio
async def test_map_story_to_owasp_returns_list_of_findings():
    with patch("app.agents.security_qa.settings.mock_mode", False):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_OWASP_MAPPING))]
            )
            result = await agent.map_story_to_owasp("SCRUM-300")

    assert len(result) == 2
    assert result[0]["owasp_category"] == "A01:2021-Broken Access Control"
    assert result[0]["status"] == "gap"
    assert result[0]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_map_story_to_owasp_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_mode", True):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.map_story_to_owasp("SCRUM-300")

    assert len(result) >= 1
    assert result[0]["notes"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_generate_rbac_matrix_returns_matrix():
    with patch("app.agents.security_qa.settings.mock_mode", False):
        agent = SecurityQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_RBAC_MATRIX))]
            )
            result = await agent.generate_rbac_matrix(
                roles=["admin", "member", "guest"],
                feature_description="Project settings page with delete and view actions",
            )

    assert result["roles"] == ["admin", "member", "guest"]
    assert len(result["matrix"]) == 2
    assert result["matrix"][0]["access"]["admin"] == "allow"


@pytest.mark.asyncio
async def test_generate_rbac_matrix_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_mode", True):
        agent = SecurityQAAgent()
        result = await agent.generate_rbac_matrix(
            roles=["admin", "member"],
            feature_description="Billing page",
        )

    assert result["roles"] == ["admin", "member"]
    assert len(result["matrix"]) >= 1
    assert result["matrix"][0]["boundary"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_generate_api_security_checklist_returns_checklist():
    with patch("app.agents.security_qa.settings.mock_mode", False):
        agent = SecurityQAAgent()
        with patch.object(agent._openapi, "parse_spec", new_callable=AsyncMock, return_value=SAMPLE_OPENAPI_SPEC), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_API_SECURITY_CHECKLIST))]
            )
            result = await agent.generate_api_security_checklist("https://example.com/openapi.json")

    assert "broken_access" in result
    assert "injection" in result
    assert "auth" in result
    assert len(result["broken_access"]) == 1


@pytest.mark.asyncio
async def test_generate_api_security_checklist_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_mode", True):
        agent = SecurityQAAgent()
        with patch.object(agent._openapi, "parse_spec", new_callable=AsyncMock, return_value=SAMPLE_OPENAPI_SPEC):
            result = await agent.generate_api_security_checklist("https://example.com/openapi.json")

    assert result["broken_access"][0].startswith("[MOCK]")
    assert "injection" in result
    assert "auth" in result
