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
