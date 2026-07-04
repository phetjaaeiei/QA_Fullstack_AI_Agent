import pytest
import json
from unittest.mock import AsyncMock, patch
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
    {"title": "Full login to dashboard flow", "type": "e2e", "steps": ["Navigate to /login", "Enter valid email", "Enter valid password", "Click Login", "Verify redirect to /dashboard", "Verify user name appears in header"], "expected_result": "User successfully completes login flow and lands on dashboard", "priority": "high"},
]


@pytest.mark.asyncio
async def test_analyze_story_returns_structured_analysis():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_ANALYSIS)):
            result = await agent.analyze_story("PROJ-123")

    assert "ambiguities" in result
    assert "missing_requirements" in result
    assert "risk_areas" in result
    assert isinstance(result["ambiguities"], list)


@pytest.mark.asyncio
async def test_analyze_story_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.analyze_story("PROJ-123")

    assert "[MOCK]" in result["ambiguities"][0]


@pytest.mark.asyncio
async def test_generate_test_cases_covers_all_types():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_TEST_CASES)):
            result = await agent.generate_test_cases("PROJ-123")

    assert len(result) >= 5
    types = {tc["type"] for tc in result}
    assert "functional" in types
    assert "negative" in types
    assert "security" in types
    assert "edge" in types
    assert "e2e" in types


@pytest.mark.asyncio
async def test_generate_test_cases_all_have_required_fields():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_TEST_CASES)):
            result = await agent.generate_test_cases("PROJ-123")

    for tc in result:
        assert "title" in tc
        assert "type" in tc
        assert "steps" in tc
        assert "expected_result" in tc
        assert "priority" in tc


@pytest.mark.asyncio
async def test_generate_test_cases_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.generate_test_cases("PROJ-123")

    assert len(result) == 5
    assert all("[MOCK]" in tc["title"] for tc in result)


MOCK_SPRINT_STORIES = [
    {"jira_id": "PROJ-121", "title": "User login", "description": "...", "acceptance_criteria": "..."},
    {"jira_id": "PROJ-122", "title": "User logout", "description": "...", "acceptance_criteria": "..."},
]

MOCK_TRACEABILITY = {
    "PROJ-121": ["Successful login", "Login with wrong password", "SQL injection in email"],
    "PROJ-122": ["Successful logout", "Session cleared after logout"],
}

MOCK_SCORE = {
    "score": 72,
    "recommendation": "conditional",
    "findings": [
        "PROJ-121 has 3 test cases — acceptable",
        "PROJ-122 missing security test cases",
        "No E2E test cases across sprint",
    ],
}


@pytest.mark.asyncio
async def test_build_traceability_map_keys_match_story_ids():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, side_effect=[
            MOCK_SPRINT_STORIES[0], MOCK_SPRINT_STORIES[1]
        ]), patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_TRACEABILITY)):
            result = await agent.build_traceability_map(["PROJ-121", "PROJ-122"])

    assert "PROJ-121" in result
    assert "PROJ-122" in result
    assert isinstance(result["PROJ-121"], list)


@pytest.mark.asyncio
async def test_score_release_readiness_returns_score_and_recommendation():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent._jira, "get_sprint_stories", new_callable=AsyncMock, return_value=MOCK_SPRINT_STORIES), \
             patch.object(agent, "generate_test_cases", new_callable=AsyncMock, return_value=MOCK_TEST_CASES), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_SCORE)):
            result = await agent.score_release_readiness("SPRINT-42")

    assert 0 <= result["score"] <= 100
    assert result["recommendation"] in ("go", "no_go", "conditional")
    assert isinstance(result["findings"], list)


@pytest.mark.asyncio
async def test_suggest_security_cases_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.suggest_security_cases(MOCK_TEST_CASES)

    assert "[MOCK]" in result[0]["title"]


@pytest.mark.asyncio
async def test_detect_coverage_gaps_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.manual_qa.settings.mock_qwen", False):
        agent = ManualQAAgent()
        with patch.object(agent._jira, "get_sprint_stories", new_callable=AsyncMock, return_value=MOCK_SPRINT_STORIES), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.detect_coverage_gaps("SPRINT-42")

    assert "[MOCK]" in result["gaps"][0]
