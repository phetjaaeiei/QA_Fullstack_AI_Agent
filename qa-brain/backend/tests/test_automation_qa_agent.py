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

# Qwen-routed calls respond in a FRAMEWORK:/CONTENT: line format, not JSON
# (see _parse_qwen_response in automation_qa.py for why). chr(92) avoids
# backslash-escaping ambiguity: it's one literal backslash character, so the
# CONTENT line contains the two-character sequence backslash+n, not a real newline.
MOCK_QWEN_RESPONSE_TEXT = (
    f"FRAMEWORK: {MOCK_SCRIPT['framework']}\n"
    f"CONTENT: {MOCK_SCRIPT['content'].replace(chr(10), chr(92) + 'n')}"
)


@pytest.mark.asyncio
async def test_call_qwen_returns_response_text():
    agent = AutomationQAAgent()
    with patch.object(agent._qwen_client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps(MOCK_SCRIPT)))]
        )
        result = await agent._call_qwen("some prompt")

    assert result == json.dumps(MOCK_SCRIPT)
    call_kwargs = mock_create.await_args.kwargs
    assert call_kwargs["model"] == agent._qwen_model
    # No system-role message and no persona/rules preamble ahead of the task
    # instructions — this model/endpoint (Qwen 3.7 via DashScope compatible-mode) is
    # intermittently unreliable (confirmed by direct testing: the identical request
    # succeeded, then failed, back to back), so requests are kept minimal defensively.
    assert call_kwargs["messages"] == [
        {"role": "user", "content": "some prompt"},
    ]


@pytest.mark.asyncio
async def test_generate_script_from_spec_returns_script():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=MOCK_QWEN_RESPONSE_TEXT):
            result = await agent.generate_script_from_spec("PROJ-200", framework="playwright")

    assert result["framework"] == "playwright"
    assert "content" in result


@pytest.mark.asyncio
async def test_generate_script_from_spec_ignores_global_mock_mode_uses_mock_qwen_instead():
    # MOCK_MODE is a global flag other (Claude-based) agents/tools still need — it must
    # stay True while ANTHROPIC_API_KEY is a placeholder. Qwen has a real key, so the
    # two Qwen-routed tools check the independent mock_qwen flag instead, letting Claude
    # stay mocked and Qwen run for real (or vice versa) at the same time.
    with patch("app.agents.automation_qa.settings.mock_mode", True), \
         patch("app.agents.automation_qa.settings.mock_qwen", False):
        agent = AutomationQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=MOCK_QWEN_RESPONSE_TEXT) as mock_call_qwen:
            result = await agent.generate_script_from_spec("PROJ-200", framework="playwright")

    mock_call_qwen.assert_awaited_once()
    assert result["framework"] == "playwright"


@pytest.mark.asyncio
async def test_generate_script_from_spec_falls_back_to_mock_when_qwen_fails():
    # Qwen 3.7 via DashScope compatible-mode is intermittently unreliable — if the
    # real call raises after its retries are exhausted, the user should still get a
    # usable (clearly-labeled) response instead of a raw error breaking the chat.
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.generate_script_from_spec("PROJ-200", framework="playwright")

    assert result["framework"] == "playwright"
    assert "[MOCK]" in result["content"]
    assert "PROJ-200" in result["content"]


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


MOCK_OPENAPI_SPEC = {
    "paths": {
        "/users/{id}": {
            "get": {"summary": "Get user by ID", "parameters": [], "responses": {"200": {}}}
        }
    }
}


@pytest.mark.asyncio
async def test_generate_script_from_spec_with_spec_url_uses_openapi_client():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        mock_parse_spec = AsyncMock(return_value=MOCK_OPENAPI_SPEC)
        with patch.object(agent._openapi, "parse_spec", mock_parse_spec), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=MOCK_QWEN_RESPONSE_TEXT):
            result = await agent.generate_script_from_spec(
                "API-SPEC-abc123", framework="playwright", spec_url="https://example.com/openapi.json"
            )

    assert result["framework"] == "playwright"
    mock_parse_spec.assert_awaited_once_with("https://example.com/openapi.json")


MOCK_OPENAPI_SPEC_VERBOSE = {
    "paths": {
        "/users/{id}": {
            "get": {
                "summary": "Get user by ID",
                "description": "Returns a single user record by their unique identifier, including profile metadata.",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {}, "404": {}},
            }
        }
    }
}


@pytest.mark.asyncio
async def test_generate_script_from_spec_with_spec_url_sends_trimmed_endpoints_to_qwen():
    # Qwen 3.7 via DashScope compatible-mode is intermittently unreliable (confirmed by
    # direct testing: the identical request succeeded, then failed, back to back) — only
    # path/method/summary are sent, dropping description/parameters/responses, to keep
    # requests minimal as a defensive measure against a flaky endpoint.
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        with patch.object(agent._openapi, "parse_spec", new_callable=AsyncMock, return_value=MOCK_OPENAPI_SPEC_VERBOSE), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=MOCK_QWEN_RESPONSE_TEXT) as mock_call_qwen:
            await agent.generate_script_from_spec(
                "API-SPEC-abc123", framework="playwright", spec_url="https://example.com/openapi.json"
            )

    sent_prompt = mock_call_qwen.await_args.args[0]
    assert "description" not in sent_prompt
    assert "parameters" not in sent_prompt
    assert "responses" not in sent_prompt
    assert '"path": "/users/{id}"' in sent_prompt
    assert '"method": "GET"' in sent_prompt
    assert '"summary": "Get user by ID"' in sent_prompt


@pytest.mark.asyncio
async def test_generate_script_from_spec_mock_mode_with_spec_url_skips_jira():
    agent = AutomationQAAgent()
    agent._mock_qwen = True
    with patch.object(agent._jira, "get_story", new_callable=AsyncMock) as mock_get_story:
        result = await agent.generate_script_from_spec(
            "API-SPEC-abc123", framework="playwright", spec_url="https://example.com/openapi.json"
        )

    mock_get_story.assert_not_called()
    assert result["framework"] == "playwright"


@pytest.mark.asyncio
async def test_crawl_site_returns_elements_from_page():
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.eval_on_selector_all = AsyncMock(return_value=[
        {"tag": "button", "text": "Submit", "type": "submit", "name": "submit-btn", "href": ""}
    ])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium = mock_chromium

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.agents.automation_qa.async_playwright", return_value=mock_cm):
        agent = AutomationQAAgent()
        pages = await agent._crawl_site("https://example.com", max_depth=1)

    assert len(pages) == 1
    assert pages[0]["url"] == "https://example.com"
    assert pages[0]["elements"][0]["text"] == "Submit"
    mock_browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_crawl_site_closes_browser_when_page_goto_raises():
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=TimeoutError("Timeout 15000ms exceeded"))
    mock_page.eval_on_selector_all = AsyncMock(return_value=[])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium = mock_chromium

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.agents.automation_qa.async_playwright", return_value=mock_cm):
        agent = AutomationQAAgent()
        with pytest.raises(TimeoutError):
            await agent._crawl_site("https://example.com", max_depth=1)

    mock_browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_crawl_site_follows_same_origin_links_within_depth():
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.eval_on_selector_all = AsyncMock(side_effect=[
        [{"tag": "a", "text": "Checkout", "type": "", "name": "", "href": "/checkout"}],
        [{"tag": "button", "text": "Pay", "type": "submit", "name": "pay-btn", "href": ""}],
    ])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium = mock_chromium

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.agents.automation_qa.async_playwright", return_value=mock_cm):
        agent = AutomationQAAgent()
        pages = await agent._crawl_site("https://example.com", max_depth=2)

    assert [p["url"] for p in pages] == ["https://example.com", "https://example.com/checkout"]


MOCK_CRAWL_PAGES = [
    {"url": "https://example.com", "elements": [
        {"tag": "button", "text": "Login", "type": "submit", "name": "login-btn", "href": ""}
    ]}
]


@pytest.mark.asyncio
async def test_explore_and_generate_returns_script():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        mock_crawl = AsyncMock(return_value=MOCK_CRAWL_PAGES)
        with patch.object(agent, "_crawl_site", mock_crawl), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=MOCK_QWEN_RESPONSE_TEXT):
            result = await agent.explore_and_generate("https://example.com", "EXPLORED-abc123")

    assert result["framework"] == "playwright"
    assert "content" in result
    mock_crawl.assert_awaited_once_with("https://example.com", max_depth=2)


@pytest.mark.asyncio
async def test_explore_and_generate_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.automation_qa.settings.mock_mode", False):
        agent = AutomationQAAgent()
        mock_crawl = AsyncMock(return_value=MOCK_CRAWL_PAGES)
        with patch.object(agent, "_crawl_site", mock_crawl), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.explore_and_generate("https://example.com", "EXPLORED-abc123")

    assert result["framework"] == "playwright"
    assert "[MOCK]" in result["content"]
    assert "EXPLORED-abc123" in result["content"]


@pytest.mark.asyncio
async def test_explore_and_generate_mock_mode_returns_mock_script_without_crawling():
    agent = AutomationQAAgent()
    agent._mock_qwen = True
    with patch.object(agent, "_crawl_site", new_callable=AsyncMock) as mock_crawl:
        result = await agent.explore_and_generate("https://example.com", "EXPLORED-abc123")

    mock_crawl.assert_not_called()
    assert result["framework"] == "playwright"
    assert "[MOCK]" in result["content"]
