import json
import re as _re
import anthropic
from app.config import settings
from app.mcp_clients.jira_client import JiraClient
from app.mcp_clients.openapi_client import OpenAPIClient


def _parse_json(text: str):
    text = text.strip()
    text = _re.sub(r"^```(?:json)?\s*", "", text)
    text = _re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _mock_test_cases(story_id: str, title: str = "") -> list[dict]:
    label = f"{story_id} ({title})" if title else story_id
    return [
        {
            "title": f"[MOCK] Successful action for {label}",
            "type": "functional",
            "steps": ["Step 1: Navigate to the feature", "Step 2: Perform the primary action", "Step 3: Verify the result"],
            "expected_result": "Action completes successfully and the expected state is shown",
            "priority": "high",
        },
        {
            "title": f"[MOCK] Reject invalid input for {label}",
            "type": "negative",
            "steps": ["Step 1: Submit the form with invalid data", "Step 2: Observe the response"],
            "expected_result": "Validation error is shown, no data is persisted",
            "priority": "high",
        },
        {
            "title": f"[MOCK] Boundary value handling for {label}",
            "type": "edge",
            "steps": ["Step 1: Submit input at the maximum allowed length", "Step 2: Submit input at the minimum allowed length"],
            "expected_result": "Both boundary values are accepted without error",
            "priority": "medium",
        },
        {
            "title": f"[MOCK] SQL injection attempt for {label}",
            "type": "security",
            "steps": ["Step 1: Enter `' OR 1=1 --` into a text field", "Step 2: Submit the form"],
            "expected_result": "Input is sanitized, no SQL error is exposed, request is rejected",
            "priority": "high",
        },
        {
            "title": f"[MOCK] End-to-end user journey for {label}",
            "type": "e2e",
            "steps": ["Step 1: Log in", "Step 2: Complete the full workflow described in the story", "Step 3: Confirm the final state"],
            "expected_result": "User completes the journey with the expected outcome at every step",
            "priority": "medium",
        },
    ]


def _mock_analysis(story_id: str, title: str = "") -> dict:
    label = f"{story_id} ({title})" if title else story_id
    return {
        "ambiguities": [f"[MOCK] Unclear what happens on {label} when input is empty"],
        "missing_requirements": [f"[MOCK] No mention of error handling for {label}"],
        "risk_areas": [f"[MOCK] Data validation and authorization for {label}"],
    }


def _mock_traceability(story_titles: dict) -> dict:
    return {
        sid: [f"[MOCK] Test case covering {sid} ({title})" if title else f"[MOCK] Test case covering {sid}"]
        for sid, title in story_titles.items()
    }


def _mock_gaps() -> dict:
    return {
        "gaps": ["[MOCK] No dedicated security test cases found", "[MOCK] No E2E coverage across the sprint"],
        "recommendations": ["[MOCK] Add SQL injection and auth-bypass test cases", "[MOCK] Add at least one full E2E scenario"],
    }


def _mock_score(sprint_id: str) -> dict:
    return {
        "score": 72,
        "recommendation": "conditional",
        "findings": [f"[MOCK] {sprint_id} has partial security coverage", "[MOCK] No E2E test cases found"],
    }


SYSTEM_PROMPT = """You are an expert Manual QA Engineer with 10+ years of experience in test design.

Your expertise:
- Test design techniques: equivalence partitioning, boundary value analysis, decision tables, state transition
- Coverage: functional, edge cases, negative cases, security abuse cases, E2E scenarios
- Risk-based testing: identify high-risk areas and prioritize accordingly
- OWASP Top 10 awareness for security test cases (especially injection, auth, access control)

Rules:
- Always return valid JSON only — no markdown, no explanation outside JSON
- Test steps must be specific and actionable (not vague like "test the feature")
- Security test cases must cover at least: SQL injection, auth bypass, unauthorized access
- Every story must have at least 1 negative test case and 1 security/abuse test case
"""


class ManualQAAgent:
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._jira = JiraClient()
        self._openapi = OpenAPIClient()
        self._model = "claude-sonnet-4-6"
        self._mock = settings.mock_mode

    async def _fetch_story_title(self, story_id: str) -> str:
        try:
            story = await self._jira.get_story(story_id)
            return story.get("title", "")
        except Exception:
            return ""

    async def analyze_story(self, story_id: str) -> dict:
        if self._mock:
            title = await self._fetch_story_title(story_id)
            return _mock_analysis(story_id, title)

        story = await self._jira.get_story(story_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Analyze this Jira story for quality risks.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

Return JSON only:
{{
  "ambiguities": ["unclear requirement or assumption that needs clarification"],
  "missing_requirements": ["requirement that is implied but not stated"],
  "risk_areas": ["area most likely to have bugs or security issues"]
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def generate_test_cases(self, story_id: str, source: str = "jira") -> list[dict]:
        if self._mock:
            title = await self._fetch_story_title(story_id)
            return _mock_test_cases(story_id, title)

        story = await self._jira.get_story(story_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=6000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Generate comprehensive test cases for this story. You MUST include all types.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

Return a JSON array. Each test case must have all these fields:
[
  {{
    "title": "concise test case name",
    "type": "functional|edge|negative|security|e2e",
    "steps": ["Step 1: specific action", "Step 2: specific action"],
    "expected_result": "what should happen if test passes",
    "priority": "high|medium|low"
  }}
]

REQUIRED coverage — you must include at least one of each type:
- functional: happy path scenarios from acceptance criteria
- negative: invalid inputs, wrong credentials, missing required fields
- edge: boundary values, empty states, max length inputs
- security: SQL injection, XSS, unauthorized access, IDOR
- e2e: full user journey from start to finish"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def suggest_security_cases(self, test_cases: list[dict]) -> list[dict]:
        if self._mock:
            return [{
                "title": "[MOCK] IDOR check on another user's resource",
                "type": "security",
                "steps": ["Step 1: Access another user's resource by ID", "Step 2: Observe the response"],
                "expected_result": "Access is denied with 403",
                "priority": "high",
            }]

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Given these existing test cases, suggest additional security and abuse test cases that are missing.

Existing test cases:
{json.dumps(test_cases, indent=2)}

Return JSON array of NEW security test cases only (don't repeat existing ones):
[
  {{
    "title": "...",
    "type": "security",
    "steps": ["..."],
    "expected_result": "...",
    "priority": "high|medium|low"
  }}
]"""
            }]
        )
        return _parse_json(response.content[0].text)

    async def build_traceability_map(self, story_ids: list[str]) -> dict:
        if self._mock:
            titles = {sid: await self._fetch_story_title(sid) for sid in story_ids}
            return _mock_traceability(titles)

        stories = []
        for story_id in story_ids:
            story = await self._jira.get_story(story_id)
            stories.append(story)

        story_summaries = "\n".join([
            f"- {s['jira_id']}: {s['title']}" for s in stories
        ])

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Create a traceability map for these stories.
For each story, list the test case titles that should cover it.

Stories:
{story_summaries}

Return JSON where keys are story IDs:
{{
  "STORY-ID": ["Test case title 1", "Test case title 2"],
  ...
}}"""
            }]
        )
        return _parse_json(response.content[0].text)

    async def detect_coverage_gaps(self, sprint_id: str) -> dict:
        if self._mock:
            return _mock_gaps()

        stories = await self._jira.get_sprint_stories(sprint_id)
        story_summaries = "\n".join([f"- {s['jira_id']}: {s['title']}" for s in stories])

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Analyze these sprint stories for test coverage gaps.

Sprint stories:
{story_summaries}

Identify what is likely missing based on common QA patterns.
Return JSON:
{{
  "gaps": ["description of missing coverage"],
  "recommendations": ["specific action to close the gap"]
}}"""
            }]
        )
        return _parse_json(response.content[0].text)

    async def score_release_readiness(self, sprint_id: str) -> dict:
        if self._mock:
            return _mock_score(sprint_id)

        stories = await self._jira.get_sprint_stories(sprint_id)
        all_test_cases = []
        for story in stories:
            tcs = await self.generate_test_cases(story["jira_id"])
            all_test_cases.extend(tcs)

        type_counts = {}
        for tc in all_test_cases:
            type_counts[tc["type"]] = type_counts.get(tc["type"], 0) + 1

        stories_summary = json.dumps(
            [{"id": s["jira_id"], "title": s["title"]} for s in stories], indent=2
        )
        type_counts_json = json.dumps(type_counts)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Evaluate release readiness for this sprint.

Sprint: {sprint_id}
Stories count: {len(stories)}
Test cases generated: {len(all_test_cases)}
Coverage by type: {type_counts_json}

Stories:
{stories_summary}

Score 0-100 based on: test coverage completeness, security coverage, negative case coverage, E2E coverage.
Return JSON:
{{
  "score": 0-100,
  "recommendation": "go|no_go|conditional",
  "findings": ["specific finding about coverage quality"]
}}"""
            }]
        )
        return _parse_json(response.content[0].text)
