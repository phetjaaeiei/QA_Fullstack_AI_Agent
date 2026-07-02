import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.automation_qa import AutomationQAAgent

MOCK_STORY = {
    "jira_id": "PROJ-200",
    "title": "User can reset password",
    "description": "As a user I want to reset my password via email",
    "acceptance_criteria": "Given a valid email, when I request reset, then I receive a reset link",
    "status": "In Progress",
}

MOCK_SCRIPT = {
    "framework": "playwright",
    "content": "import { test } from '@playwright/test';\n",
}


@pytest.mark.asyncio
async def test_generate_script_from_spec_returns_script():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_SCRIPT))]
            )
            result = await agent.generate_script_from_spec("PROJ-200", framework="playwright")

    assert result["framework"] == "playwright"
    assert "content" in result


@pytest.mark.asyncio
async def test_apply_company_framework_returns_reformatted_script():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps({"content": "reformatted"}))]
            )
            result = await agent.apply_company_framework("raw script")

    assert result["content"] == "reformatted"


@pytest.mark.asyncio
async def test_load_house_style_falls_back_when_file_missing(tmp_path):
    from app.agents.automation_qa import _load_house_style
    missing_path = tmp_path / "does-not-exist.md"
    assert "best practices" in _load_house_style(missing_path)


@pytest.mark.asyncio
async def test_load_house_style_reads_existing_file(tmp_path):
    from app.agents.automation_qa import _load_house_style
    style_path = tmp_path / "automation-standards.md"
    style_path.write_text("Use camelCase for test names.")
    assert _load_house_style(style_path) == "Use camelCase for test names."


@pytest.mark.asyncio
async def test_suggest_self_healing_returns_alternatives():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        mock_page_response = MagicMock()
        mock_page_response.text = "<html><body><button id='submit-1'>Submit</button></body></html>"
        mock_page_response.raise_for_status = lambda: None

        with patch.object(agent._http, "get", new_callable=AsyncMock, return_value=mock_page_response), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps({
                    "alternatives": ["getByTestId('submit-1')"],
                    "strategy": "prefer test-id",
                }))]
            )
            result = await agent.suggest_self_healing("#submit-1", "https://example.com/checkout")

    assert result["alternatives"] == ["getByTestId('submit-1')"]
    assert "strategy" in result


MOCK_CI_RUN = {
    "run_id": "123456",
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/acme/repo/actions/runs/123456",
    "jobs": [{"name": "e2e-tests", "conclusion": "failure", "steps": []}],
}


@pytest.mark.asyncio
async def test_classify_failure_returns_root_cause():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._github, "get_test_results", new_callable=AsyncMock, return_value=MOCK_CI_RUN), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps({
                    "root_cause": "Script",
                    "explanation": "stale locator",
                    "failed_step": "click submit",
                }))]
            )
            result = await agent.classify_failure("acme/repo", "123456")

    assert result["root_cause"] == "Script"


@pytest.mark.asyncio
async def test_auto_fix_script_returns_fixed_content():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps({
                    "content": "fixed script",
                    "explanation": "replaced brittle locator",
                }))]
            )
            result = await agent.auto_fix_script("broken script", "TimeoutError: locator not found")

    assert result["content"] == "fixed script"
    assert "explanation" in result


MOCK_TEST_DATA = [
    {"label": "Valid boundary", "value": "typical valid input"},
    {"label": "Invalid input", "value": "malformed input expected to be rejected"},
]

MOCK_TRACEABILITY_MAPPING = {
    "story_id": "PROJ-200",
    "covers_acceptance_criteria": True,
    "confidence": "high",
    "notes": "Covers the happy path described in the acceptance criteria",
}


@pytest.mark.asyncio
async def test_generate_test_data_returns_list():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_TEST_DATA))]
            )
            result = await agent.generate_test_data("Email field must accept valid emails and reject invalid ones")

    assert len(result) == 2
    assert result[0]["label"] == "Valid boundary"


@pytest.mark.asyncio
async def test_map_script_traceability_returns_mapping():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_TRACEABILITY_MAPPING))]
            )
            result = await agent.map_script_traceability("PROJ-200", "test('reset password', async () => {});")

    assert result["story_id"] == "PROJ-200"
    assert result["covers_acceptance_criteria"] is True
