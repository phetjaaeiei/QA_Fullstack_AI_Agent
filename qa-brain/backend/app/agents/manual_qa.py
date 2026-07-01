import json
import anthropic
from app.config import settings
from app.mcp_clients.jira_client import JiraClient
from app.mcp_clients.openapi_client import OpenAPIClient

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
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._jira = JiraClient()
        self._openapi = OpenAPIClient()
        self._model = "claude-sonnet-4-6"

    async def analyze_story(self, story_id: str) -> dict:
        story = await self._jira.get_story(story_id)

        response = self._client.messages.create(
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

        return json.loads(response.content[0].text)

    async def generate_test_cases(self, story_id: str, source: str = "jira") -> list[dict]:
        story = await self._jira.get_story(story_id)

        response = self._client.messages.create(
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

        return json.loads(response.content[0].text)

    async def suggest_security_cases(self, test_cases: list[dict]) -> list[dict]:
        response = self._client.messages.create(
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
        return json.loads(response.content[0].text)

    async def build_traceability_map(self, story_ids: list[str]) -> dict:
        stories = []
        for story_id in story_ids:
            story = await self._jira.get_story(story_id)
            stories.append(story)

        story_summaries = "\n".join([
            f"- {s['jira_id']}: {s['title']}" for s in stories
        ])

        response = self._client.messages.create(
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
        return json.loads(response.content[0].text)

    async def detect_coverage_gaps(self, sprint_id: str) -> dict:
        stories = await self._jira.get_sprint_stories(sprint_id)
        story_summaries = "\n".join([f"- {s['jira_id']}: {s['title']}" for s in stories])

        response = self._client.messages.create(
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
        return json.loads(response.content[0].text)

    async def score_release_readiness(self, sprint_id: str) -> dict:
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

        response = self._client.messages.create(
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
        return json.loads(response.content[0].text)
