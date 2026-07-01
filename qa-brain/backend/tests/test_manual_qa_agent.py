import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.manual_qa import ManualQAAgent

MOCK_STORY = {
    "jira_id": "PROJ-123",
    "title": "User can login with email and password",
    "description": "As a user I want to login with email and password to access the system",
    "acceptance_criteria": "Given valid credentials, when I submit login form, then I am redirected to dashboard",
    "status": "In Progress",
}

MOCK_ANALYSIS = {
    "ambiguities": ["What happens if email is not registered?", "Is there a lockout after failed attempts?"],
    "missing_requirements": ["Password reset flow", "Remember me functionality"],
    "risk_areas": ["Authentication security", "Session management"],
}

MOCK_TEST_CASES = [
    {"title": "Successful login with valid credentials", "type": "functional", "steps": ["Navigate to /login", "Enter valid email", "Enter valid password", "Click Login"], "expected_result": "User is redirected to /dashboard", "priority": "high"},
    {"title": "Login with incorrect password", "type": "negative", "steps": ["Navigate to /login", "Enter valid email", "Enter wrong password", "Click Login"], "expected_result": "Error message 'Invalid credentials' is shown", "priority": "high"},
    {"title": "SQL injection in email field", "type": "security", "steps": ["Navigate to /login", "Enter `' OR 1=1 --` in email", "Enter any password", "Click Login"], "expected_result": "Login fails, no SQL error exposed", "priority": "high"},
    {"title": "Login with empty fields", "type": "edge", "steps": ["Navigate to /login", "Leave email empty", "Leave password empty", "Click Login"], "expected_result": "Validation errors shown for both fields", "priority": "medium"},
]


@pytest.mark.asyncio
async def test_analyze_story_returns_structured_analysis():
    agent = ManualQAAgent()
    with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
         patch.object(agent._client.messages, "create") as mock_create:
        mock_create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(MOCK_ANALYSIS))]
        )
        result = await agent.analyze_story("PROJ-123")

    assert "ambiguities" in result
    assert "missing_requirements" in result
    assert "risk_areas" in result
    assert isinstance(result["ambiguities"], list)


@pytest.mark.asyncio
async def test_generate_test_cases_covers_all_types():
    agent = ManualQAAgent()
    with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
         patch.object(agent._client.messages, "create") as mock_create:
        mock_create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(MOCK_TEST_CASES))]
        )
        result = await agent.generate_test_cases("PROJ-123")

    assert len(result) >= 4
    types = {tc["type"] for tc in result}
    assert "functional" in types
    assert "negative" in types
    assert "security" in types
    assert "edge" in types


@pytest.mark.asyncio
async def test_generate_test_cases_all_have_required_fields():
    agent = ManualQAAgent()
    with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
         patch.object(agent._client.messages, "create") as mock_create:
        mock_create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(MOCK_TEST_CASES))]
        )
        result = await agent.generate_test_cases("PROJ-123")

    for tc in result:
        assert "title" in tc
        assert "type" in tc
        assert "steps" in tc
        assert "expected_result" in tc
        assert "priority" in tc
