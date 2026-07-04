import asyncio
import json
import re as _re
import anthropic
from openai import AsyncOpenAI
from app.config import settings
from app.mcp_clients.jira_client import JiraClient
from app.mcp_clients.openapi_client import OpenAPIClient


def _parse_json(text: str):
    text = text.strip()
    text = _re.sub(r"^```(?:json)?\s*", "", text)
    text = _re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


# One call per type instead of one call asking for all 5 at once — live testing on
# 2026-07-05 showed Qwen's response time scales with how much output it has to
# generate, not prompt size: a 1-item request succeeded in ~17s while a 5-item
# request timed out at 60s+ every time. Smaller asks succeed more often.
_TEST_CASE_TYPES = [
    ("functional", "a happy path scenario derived directly from the acceptance criteria"),
    ("negative", "an invalid input, wrong credentials, or missing required field"),
    ("edge", "a boundary value, empty state, or maximum length input"),
    ("security", "an SQL injection, XSS, unauthorized access, or IDOR attempt"),
    ("e2e", "the full user journey through this feature from start to finish"),
]

_MOCK_TEST_CASE_TEMPLATES = {
    "functional": {
        "title": "[MOCK] Successful action for {label}",
        "steps": ["Step 1: Navigate to the feature", "Step 2: Perform the primary action", "Step 3: Verify the result"],
        "expected_result": "Action completes successfully and the expected state is shown",
        "priority": "high",
    },
    "negative": {
        "title": "[MOCK] Reject invalid input for {label}",
        "steps": ["Step 1: Submit the form with invalid data", "Step 2: Observe the response"],
        "expected_result": "Validation error is shown, no data is persisted",
        "priority": "high",
    },
    "edge": {
        "title": "[MOCK] Boundary value handling for {label}",
        "steps": ["Step 1: Submit input at the maximum allowed length", "Step 2: Submit input at the minimum allowed length"],
        "expected_result": "Both boundary values are accepted without error",
        "priority": "medium",
    },
    "security": {
        "title": "[MOCK] SQL injection attempt for {label}",
        "steps": ["Step 1: Enter `' OR 1=1 --` into a text field", "Step 2: Submit the form"],
        "expected_result": "Input is sanitized, no SQL error is exposed, request is rejected",
        "priority": "high",
    },
    "e2e": {
        "title": "[MOCK] End-to-end user journey for {label}",
        "steps": ["Step 1: Log in", "Step 2: Complete the full workflow described in the story", "Step 3: Confirm the final state"],
        "expected_result": "User completes the journey with the expected outcome at every step",
        "priority": "medium",
    },
}


def _mock_test_case_for_type(type_name: str, story_id: str, title: str = "") -> dict:
    label = f"{story_id} ({title})" if title else story_id
    template = _MOCK_TEST_CASE_TEMPLATES[type_name]
    return {
        "title": template["title"].format(label=label),
        "type": type_name,
        "steps": template["steps"],
        "expected_result": template["expected_result"],
        "priority": template["priority"],
    }


def _mock_test_cases(story_id: str, title: str = "") -> list[dict]:
    return [_mock_test_case_for_type(type_name, story_id, title) for type_name, _ in _TEST_CASE_TYPES]


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


# One call per attack vector instead of one open-ended "suggest some cases" call —
# same output-size-scaling problem as _TEST_CASE_TYPES above.
_SECURITY_SUGGESTION_VECTORS = [
    ("idor", "an IDOR (insecure direct object reference) — accessing another user's resource by changing an ID"),
    ("auth_bypass", "an authentication bypass or reuse of an invalidated session"),
    ("privilege_escalation", "a lower-privilege role performing an action reserved for a higher-privilege role"),
    ("injection", "an SQL, command, or NoSQL injection through user-supplied input"),
    ("xss", "a reflected or stored cross-site scripting (XSS) attempt through user-supplied input"),
]

_MOCK_SECURITY_SUGGESTION_TEMPLATES = {
    "idor": {
        "title": "[MOCK] IDOR check on another user's resource",
        "steps": ["Step 1: Access another user's resource by ID", "Step 2: Observe the response"],
        "expected_result": "Access is denied with 403",
        "priority": "high",
    },
    "auth_bypass": {
        "title": "[MOCK] Session reuse after logout",
        "steps": ["Step 1: Log in and capture the session token", "Step 2: Log out, then reuse the captured token"],
        "expected_result": "The reused session is rejected",
        "priority": "high",
    },
    "privilege_escalation": {
        "title": "[MOCK] Lower-privilege role attempts a restricted action",
        "steps": ["Step 1: Authenticate as a low-privilege role", "Step 2: Call the endpoint reserved for a higher-privilege role"],
        "expected_result": "Access is denied with 403",
        "priority": "high",
    },
    "injection": {
        "title": "[MOCK] Injection attempt through a user-supplied field",
        "steps": ["Step 1: Submit a payload containing SQL/command injection characters", "Step 2: Observe the response"],
        "expected_result": "Input is sanitized/rejected, no injection occurs",
        "priority": "high",
    },
    "xss": {
        "title": "[MOCK] Stored XSS attempt through a user-supplied field",
        "steps": ["Step 1: Submit a `<script>` payload in a text field", "Step 2: View the page where that field is rendered"],
        "expected_result": "The payload is escaped/sanitized and does not execute",
        "priority": "high",
    },
}


def _mock_security_suggestion_for_vector(vector_key: str) -> dict:
    template = _MOCK_SECURITY_SUGGESTION_TEMPLATES[vector_key]
    return {
        "title": template["title"],
        "type": "security",
        "steps": template["steps"],
        "expected_result": template["expected_result"],
        "priority": template["priority"],
    }


def _mock_suggested_security_cases() -> list[dict]:
    return [_mock_security_suggestion_for_vector(key) for key, _ in _SECURITY_SUGGESTION_VECTORS]


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
        # Qwen is intermittently unreliable (see automation_qa.py's _call_qwen for the
        # full investigation) — short timeout + one retry bounds worst-case latency;
        # every call site below falls back to the existing mock data on failure.
        self._qwen_client = AsyncOpenAI(
            base_url=settings.qwen_base_url, api_key=settings.qwen_api_key, timeout=60.0, max_retries=1
        )
        self._qwen_model = settings.qwen_model
        self._mock_qwen = settings.mock_qwen

    async def _call_qwen(self, prompt_content: str, max_tokens: int = 4000) -> str:
        # No system-role message and no persona/rules preamble ahead of the task
        # instructions (see automation_qa.py's _call_qwen) — send only the task prompt.
        response = await self._qwen_client.chat.completions.create(
            model=self._qwen_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt_content}],
        )
        return response.choices[0].message.content

    async def _fetch_story_title(self, story_id: str) -> str:
        try:
            story = await self._jira.get_story(story_id)
            return story.get("title", "")
        except Exception:
            return ""

    async def analyze_story(self, story_id: str) -> dict:
        if self._mock_qwen:
            title = await self._fetch_story_title(story_id)
            return _mock_analysis(story_id, title)

        story = await self._jira.get_story(story_id)

        prompt_content = f"""Analyze this Jira story for quality risks.

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

        try:
            text = await self._call_qwen(prompt_content, max_tokens=2000)
            return _parse_json(text)
        except Exception:
            return _mock_analysis(story_id, story.get("title", ""))

    async def _generate_one_test_case(self, story: dict, type_name: str, guidance: str) -> dict:
        prompt_content = f"""Generate exactly 1 {type_name} test case for this story.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

Focus: {guidance}

Return a single JSON object only (not an array, no markdown):
{{
  "title": "concise test case name",
  "type": "{type_name}",
  "steps": ["Step 1: specific action", "Step 2: specific action"],
  "expected_result": "what should happen if test passes",
  "priority": "high|medium|low"
}}"""

        try:
            text = await self._call_qwen(prompt_content, max_tokens=800)
            return _parse_json(text)
        except Exception:
            return _mock_test_case_for_type(type_name, story["jira_id"], story.get("title", ""))

    async def generate_test_cases(self, story_id: str, source: str = "jira") -> list[dict]:
        if self._mock_qwen:
            title = await self._fetch_story_title(story_id)
            return _mock_test_cases(story_id, title)

        story = await self._jira.get_story(story_id)

        return list(await asyncio.gather(*[
            self._generate_one_test_case(story, type_name, guidance)
            for type_name, guidance in _TEST_CASE_TYPES
        ]))

    async def _suggest_one_security_case(self, test_cases: list[dict], vector_key: str, vector_description: str) -> dict | None:
        prompt_content = f"""Given these existing test cases, check whether this attack vector is already covered: {vector_description}.

Existing test cases:
{json.dumps(test_cases, indent=2)}

If it is already covered, respond with exactly {{"already_covered": true}}.
Otherwise return a single new JSON object only (not an array, no markdown):
{{
  "title": "...",
  "type": "security",
  "steps": ["..."],
  "expected_result": "...",
  "priority": "high|medium|low"
}}"""

        try:
            text = await self._call_qwen(prompt_content, max_tokens=600)
            parsed = _parse_json(text)
            if isinstance(parsed, dict) and parsed.get("already_covered"):
                return None
            return parsed
        except Exception:
            return _mock_security_suggestion_for_vector(vector_key)

    async def suggest_security_cases(self, test_cases: list[dict]) -> list[dict]:
        if self._mock_qwen:
            return _mock_suggested_security_cases()

        results = await asyncio.gather(*[
            self._suggest_one_security_case(test_cases, vector_key, vector_description)
            for vector_key, vector_description in _SECURITY_SUGGESTION_VECTORS
        ])
        return [r for r in results if r is not None]

    async def build_traceability_map(self, story_ids: list[str]) -> dict:
        if self._mock_qwen:
            titles = {sid: await self._fetch_story_title(sid) for sid in story_ids}
            return _mock_traceability(titles)

        stories = []
        for story_id in story_ids:
            story = await self._jira.get_story(story_id)
            stories.append(story)

        story_summaries = "\n".join([
            f"- {s['jira_id']}: {s['title']}" for s in stories
        ])

        prompt_content = f"""Create a traceability map for these stories.
For each story, list the test case titles that should cover it.

Stories:
{story_summaries}

Return JSON where keys are story IDs:
{{
  "STORY-ID": ["Test case title 1", "Test case title 2"],
  ...
}}"""

        try:
            text = await self._call_qwen(prompt_content, max_tokens=3000)
            return _parse_json(text)
        except Exception:
            titles = {s["jira_id"]: s.get("title", "") for s in stories}
            return _mock_traceability(titles)

    async def detect_coverage_gaps(self, sprint_id: str) -> dict:
        if self._mock_qwen:
            return _mock_gaps()

        stories = await self._jira.get_sprint_stories(sprint_id)
        story_summaries = "\n".join([f"- {s['jira_id']}: {s['title']}" for s in stories])

        prompt_content = f"""Analyze these sprint stories for test coverage gaps.

Sprint stories:
{story_summaries}

Identify what is likely missing based on common QA patterns.
Return JSON:
{{
  "gaps": ["description of missing coverage"],
  "recommendations": ["specific action to close the gap"]
}}"""

        try:
            text = await self._call_qwen(prompt_content, max_tokens=2000)
            return _parse_json(text)
        except Exception:
            return _mock_gaps()

    async def score_release_readiness(self, sprint_id: str) -> dict:
        if self._mock_qwen:
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

        prompt_content = f"""Evaluate release readiness for this sprint.

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

        try:
            text = await self._call_qwen(prompt_content, max_tokens=2000)
            return _parse_json(text)
        except Exception:
            return _mock_score(sprint_id)
