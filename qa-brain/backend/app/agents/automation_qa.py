import json
import re as _re
from pathlib import Path
from urllib.parse import urljoin, urlparse
import httpx
import anthropic
from playwright.async_api import async_playwright
from app.config import settings
from app.mcp_clients.jira_client import JiraClient
from app.mcp_clients.github_client import GitHubClient
from app.mcp_clients.openapi_client import OpenAPIClient


def _parse_json(text: str):
    text = text.strip()
    text = _re.sub(r"^```(?:json)?\s*", "", text)
    text = _re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


_HOUSE_STYLE_PATH = Path(__file__).resolve().parents[2] / "docs" / "automation-standards.md"


def _load_house_style(path: Path = _HOUSE_STYLE_PATH) -> str:
    if path.exists():
        return path.read_text()
    return "No house style defined yet — use general Playwright/Robot Framework best practices."


SYSTEM_PROMPT = """You are an expert Automation QA Engineer with 10+ years of experience in test automation.

Your expertise:
- Playwright (TypeScript) and Robot Framework script authoring
- Page Object Model design and locator strategy
- CI test failure triage: distinguishing Bug / Data / Env / Script issues
- Self-healing locator strategies and flaky test diagnosis

Rules:
- Always return valid JSON only — no markdown, no explanation outside JSON
- Generated scripts must be syntactically valid for the requested framework
- Locator suggestions must be specific (prefer role/test-id selectors over brittle CSS/XPath)
"""


def _mock_script(story_id: str, framework: str, title: str = "") -> dict:
    label = f"{story_id} ({title})" if title else story_id
    if framework == "robot":
        content = (
            "*** Settings ***\n"
            "Library    SeleniumLibrary\n\n"
            "*** Test Cases ***\n"
            f"[MOCK] Verify {label}\n"
            "    Open Browser    https://example.com    chrome\n"
            "    Wait Until Element Is Visible    id=main\n"
            "    Close Browser\n"
        )
    else:
        content = (
            "import { test, expect } from '@playwright/test';\n\n"
            f"test('[MOCK] Verify {label}', async ({{ page }}) => {{\n"
            "  await page.goto('https://example.com');\n"
            "  await expect(page.getByRole('main')).toBeVisible();\n"
            "});\n"
        )
    return {"framework": framework, "content": content}


class AutomationQAAgent:
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._jira = JiraClient()
        self._github = GitHubClient()
        self._openapi = OpenAPIClient()
        self._http = httpx.AsyncClient(timeout=15.0)
        self._model = "claude-sonnet-4-6"
        self._mock = settings.mock_mode

    async def _crawl_site(self, start_url: str, max_depth: int = 2) -> list:
        visited = set()
        to_visit = [(start_url, 1)]
        pages_summary = []
        origin = urlparse(start_url).netloc

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            while to_visit and len(visited) < 5:
                url, depth = to_visit.pop(0)
                if url in visited or depth > max_depth:
                    continue
                visited.add(url)

                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                elements = await page.eval_on_selector_all(
                    "a[href], button, input, select, textarea, [role=button]",
                    """els => els.map(el => ({
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || '').trim().slice(0, 80),
                        type: el.getAttribute('type') || '',
                        name: el.getAttribute('name') || el.id || '',
                        href: el.getAttribute('href') || '',
                    }))""",
                )
                pages_summary.append({"url": url, "elements": elements})

                if depth < max_depth:
                    for el in elements:
                        href = el.get("href") or ""
                        if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                            next_url = urljoin(url, href)
                            if urlparse(next_url).netloc == origin and next_url not in visited:
                                to_visit.append((next_url, depth + 1))

            await browser.close()

        return pages_summary

    async def _fetch_story_title(self, story_id: str) -> str:
        try:
            story = await self._jira.get_story(story_id)
            return story.get("title", "")
        except Exception:
            return ""

    async def generate_script_from_spec(self, story_id: str, framework: str = "playwright", spec_url: str = None) -> dict:
        if self._mock:
            title = "" if spec_url else await self._fetch_story_title(story_id)
            return _mock_script(story_id, framework, title)

        if spec_url:
            spec = await self._openapi.parse_spec(spec_url)
            endpoints = self._openapi.list_endpoints(spec)
            prompt_content = f"""Generate a {framework} test script skeleton covering these API endpoints.

Endpoints:
{json.dumps(endpoints, indent=2)}

Return JSON only:
{{
  "framework": "{framework}",
  "content": "the full script source code, using \\n for newlines"
}}"""
        else:
            story = await self._jira.get_story(story_id)
            prompt_content = f"""Generate a {framework} test script skeleton for this story.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

Return JSON only:
{{
  "framework": "{framework}",
  "content": "the full script source code, using \\n for newlines"
}}"""

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt_content}]
        )

        return _parse_json(response.content[0].text)

    async def apply_company_framework(self, script_content: str) -> dict:
        if self._mock:
            return {"content": f"// [MOCK] reformatted to house style\n{script_content}"}

        house_style = _load_house_style()

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Reformat this script to follow the house style below. Keep the test logic identical — only change structure, naming, and organization.

House style:
{house_style}

Script:
{script_content}

Return JSON only:
{{
  "content": "the reformatted script source code, using \\n for newlines"
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def suggest_self_healing(self, broken_locator: str, page_url: str) -> dict:
        if self._mock:
            return {
                "alternatives": [
                    f"[MOCK] getByRole('button') — replaces {broken_locator}",
                    "[MOCK] getByTestId('submit-btn')",
                    "[MOCK] locator('button[type=submit]')",
                ],
                "strategy": "[MOCK] Prefer role/test-id selectors over brittle CSS paths",
            }

        page_response = await self._http.get(page_url)
        page_response.raise_for_status()
        page_html = page_response.text[:8000]

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""This locator is broken: {broken_locator}

Page HTML (truncated):
{page_html}

Suggest 3-5 alternative locators and a strategy.
Return JSON only:
{{
  "alternatives": ["alternative locator 1", "alternative locator 2"],
  "strategy": "why these are more resilient"
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def classify_failure(self, repo: str, run_id: str) -> dict:
        if self._mock:
            return {
                "root_cause": "Script",
                "explanation": f"[MOCK] Locator timeout in CI run {run_id} — likely a stale selector, not a product bug",
                "failed_step": "[MOCK] Click submit button",
            }

        run_data = await self._github.get_test_results(repo, run_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Classify the root cause of this CI test failure.

CI run data:
{json.dumps(run_data, indent=2)}

Return JSON only:
{{
  "root_cause": "Bug|Data|Env|Script",
  "explanation": "why you classified it this way",
  "failed_step": "the specific step that failed"
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def auto_fix_script(self, script_content: str, error_message: str) -> dict:
        if self._mock:
            return {
                "content": f"// [MOCK] auto-fixed\n{script_content}",
                "explanation": "[MOCK] Replaced the brittle locator with a role-based selector",
            }

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""This script failed with the error below. Fix it.

Script:
{script_content}

Error:
{error_message}

Return JSON only:
{{
  "content": "the fixed script source code, using \\n for newlines",
  "explanation": "what was wrong and how you fixed it"
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def generate_test_data(self, requirements: str) -> list:
        if self._mock:
            return [
                {"label": "[MOCK] Valid boundary", "value": "typical valid input"},
                {"label": "[MOCK] Minimum boundary", "value": "shortest allowed input"},
                {"label": "[MOCK] Maximum boundary", "value": "longest allowed input"},
                {"label": "[MOCK] Invalid input", "value": "malformed input expected to be rejected"},
            ]

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Generate test data sets and boundary variations for this requirement.

Requirement:
{requirements}

Return a JSON array:
[
  {{"label": "short description of the data set", "value": "the actual test data value"}}
]"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def map_script_traceability(self, story_id: str, script_content: str) -> dict:
        if self._mock:
            return {
                "story_id": story_id,
                "covers_acceptance_criteria": True,
                "confidence": "medium",
                "notes": "[MOCK] Script appears to cover the story's happy path",
            }

        story = await self._jira.get_story(story_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Given this automation script and the story it's meant to cover, assess whether the script covers the story's acceptance criteria.

Story ID: {story['jira_id']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

Script:
{script_content}

Return JSON only:
{{
  "story_id": "{story['jira_id']}",
  "covers_acceptance_criteria": true or false,
  "confidence": "high|medium|low",
  "notes": "brief explanation"
}}"""
            }]
        )

        return _parse_json(response.content[0].text)
