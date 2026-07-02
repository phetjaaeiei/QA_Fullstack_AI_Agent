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


OWASP_CATEGORIES = [
    "A01:2021-Broken Access Control",
    "A02:2021-Cryptographic Failures",
    "A03:2021-Injection",
    "A04:2021-Insecure Design",
    "A05:2021-Security Misconfiguration",
    "A06:2021-Vulnerable and Outdated Components",
    "A07:2021-Identification and Authentication Failures",
    "A08:2021-Software and Data Integrity Failures",
    "A09:2021-Security Logging and Monitoring Failures",
    "A10:2021-Server-Side Request Forgery",
]


def _mock_owasp_test_cases(story_id: str, title: str = "") -> list:
    label = f"{story_id} ({title})" if title else story_id
    return [
        {
            "title": f"[MOCK] Unauthorized access attempt on {label}",
            "type": "security",
            "owasp_category": "A01:2021-Broken Access Control",
            "steps": ["Step 1: Authenticate as a low-privilege user", "Step 2: Attempt to access a restricted resource"],
            "expected_result": "Access is denied with 403",
            "priority": "high",
        },
        {
            "title": f"[MOCK] Injection attempt on {label}",
            "type": "security",
            "owasp_category": "A03:2021-Injection",
            "steps": ["Step 1: Submit a payload containing SQL/command injection characters", "Step 2: Observe the response"],
            "expected_result": "Input is sanitized/rejected, no injection occurs",
            "priority": "high",
        },
        {
            "title": f"[MOCK] Weak authentication check on {label}",
            "type": "security",
            "owasp_category": "A07:2021-Identification and Authentication Failures",
            "steps": ["Step 1: Attempt login with a weak/leaked password", "Step 2: Attempt session reuse after logout"],
            "expected_result": "Weak credentials are rejected and sessions are invalidated on logout",
            "priority": "medium",
        },
    ]


def _mock_owasp_mapping(story_id: str, title: str = "") -> list:
    label = f"{story_id} ({title})" if title else story_id
    return [
        {
            "owasp_category": "A01:2021-Broken Access Control",
            "status": "gap",
            "risk_level": "high",
            "notes": f"[MOCK] No explicit authorization check identified for {label}",
        },
        {
            "owasp_category": "A03:2021-Injection",
            "status": "covered",
            "risk_level": "medium",
            "notes": f"[MOCK] Input validation appears present for {label}",
        },
        {
            "owasp_category": "A05:2021-Security Misconfiguration",
            "status": "not_applicable",
            "risk_level": "low",
            "notes": f"[MOCK] No configuration surface identified for {label}",
        },
    ]


SYSTEM_PROMPT = """You are an expert Security QA Engineer with deep expertise in application security testing.

Your expertise:
- OWASP Top 10 (2021) categories and how they manifest in typical web/API features
- Threat modeling: identifying attack surfaces from feature descriptions
- Access control testing: RBAC, IDOR, privilege escalation
- Injection testing: SQLi, XSS, command injection, SSRF
- Vulnerability triage: CVSS scoring, false-positive identification

Rules:
- Always return valid JSON only — no markdown, no explanation outside JSON
- OWASP category values must exactly match the 2021 Top 10 naming, e.g. "A01:2021-Broken Access Control"
- Test steps must be specific and actionable (not vague like "test for vulnerabilities")
- Be conservative but thorough: flag genuine risk, don't manufacture findings for categories that clearly don't apply
"""


class SecurityQAAgent:
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._jira = JiraClient()
        self._openapi = OpenAPIClient()
        self._model = "claude-opus-4-8"
        self._mock = settings.mock_mode

    async def _fetch_story_title(self, story_id: str) -> str:
        try:
            story = await self._jira.get_story(story_id)
            return story.get("title", "")
        except Exception:
            return ""

    async def generate_owasp_test_cases(self, story_id: str) -> list:
        if self._mock:
            title = await self._fetch_story_title(story_id)
            return _mock_owasp_test_cases(story_id, title)

        story = await self._jira.get_story(story_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Generate OWASP Top 10 security test cases relevant to this story. Only include categories that plausibly apply to the described feature.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

OWASP Top 10 (2021) categories to choose from:
{json.dumps(OWASP_CATEGORIES, indent=2)}

Return a JSON array. Each test case must have all these fields:
[
  {{
    "title": "concise test case name",
    "type": "security",
    "owasp_category": "exact OWASP category string from the list above",
    "steps": ["Step 1: specific action", "Step 2: specific action"],
    "expected_result": "what should happen if the system correctly defends against this",
    "priority": "high|medium|low"
  }}
]"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def map_story_to_owasp(self, story_id: str) -> list:
        if self._mock:
            title = await self._fetch_story_title(story_id)
            return _mock_owasp_mapping(story_id, title)

        story = await self._jira.get_story(story_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Assess this story against each OWASP Top 10 (2021) category and determine risk coverage.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

OWASP Top 10 (2021) categories to assess:
{json.dumps(OWASP_CATEGORIES, indent=2)}

For each category that is plausibly relevant to this story (skip categories that clearly do not apply), return one finding.
Return a JSON array:
[
  {{
    "owasp_category": "exact OWASP category string from the list above",
    "status": "covered|gap|not_applicable",
    "risk_level": "critical|high|medium|low",
    "notes": "brief explanation of why this status/risk was assigned"
  }}
]"""
            }]
        )

        return _parse_json(response.content[0].text)
