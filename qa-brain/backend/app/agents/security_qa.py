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

    async def generate_rbac_matrix(self, roles: list, feature_description: str) -> dict:
        if self._mock:
            return {
                "roles": roles,
                "matrix": [
                    {
                        "boundary": f"[MOCK] Access boundary for: {feature_description[:60]}",
                        "access": {role: ("allow" if role == roles[0] else "deny") for role in roles},
                    }
                ],
            }

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Build a role-based access control (RBAC) test matrix for this feature.

Roles: {json.dumps(roles)}
Feature description: {feature_description}

For each meaningful access boundary (an action or resource whose access should differ by role), determine whether each role should be allowed or denied.
Return JSON only:
{{
  "roles": {json.dumps(roles)},
  "matrix": [
    {{
      "boundary": "description of the access boundary being tested",
      "access": {{"role_name": "allow|deny", ...}}
    }}
  ]
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def generate_api_security_checklist(self, spec_url_or_path: str) -> dict:
        if self._mock:
            spec = await self._openapi.parse_spec(spec_url_or_path)
            endpoints = self._openapi.list_endpoints(spec)
            first_path = endpoints[0]["path"] if endpoints else "the API"
            return {
                "broken_access": [f"[MOCK] Verify {first_path} enforces per-resource authorization"],
                "injection": [f"[MOCK] Verify {first_path} validates and sanitizes all path/query parameters"],
                "auth": [f"[MOCK] Verify {first_path} requires a valid authenticated session"],
            }

        spec = await self._openapi.parse_spec(spec_url_or_path)
        endpoints = self._openapi.list_endpoints(spec)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Generate a security checklist for this API's endpoints, organized by OWASP risk area.

Endpoints:
{json.dumps(endpoints, indent=2)}

Return JSON only:
{{
  "broken_access": ["checklist item covering authorization/IDOR risks"],
  "injection": ["checklist item covering injection risks"],
  "auth": ["checklist item covering authentication risks"]
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def triage_vulnerabilities(self, scan_json: str) -> dict:
        if self._mock:
            return {
                "prioritized": [
                    {"finding": "[MOCK] Highest-severity finding from the pasted scan output", "severity": "high", "cvss_estimate": 7.5},
                ],
                "false_positives": ["[MOCK] Low-signal finding likely already mitigated"],
            }

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Triage this vulnerability scanner output. The JSON structure is scanner-agnostic — infer field meaning from context.

Scanner output:
{scan_json}

Rank real findings by priority and flag likely false positives.
Return JSON only:
{{
  "prioritized": [
    {{"finding": "description of the finding", "severity": "critical|high|medium|low", "cvss_estimate": 0.0}}
  ],
  "false_positives": ["description of a finding that is likely a false positive, and why"]
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def write_security_defect(self, finding: str, project_key: str = "SCRUM") -> dict:
        if self._mock:
            return {
                "report": f"[MOCK] Security defect report for: {finding[:80]}",
                "impact": "[MOCK] Potential unauthorized data access or system compromise",
                "cvss_score": 7.5,
                "evidence": f"[MOCK] Evidence extracted from: {finding[:80]}",
                "jira_id": "[MOCK] SCRUM-999",
                "url": "[MOCK]",
            }

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Turn this vulnerability finding into a structured security defect report.

Finding:
{finding}

Return JSON only:
{{
  "report": "concise defect title/summary",
  "impact": "what an attacker could achieve by exploiting this",
  "cvss_score": 0.0,
  "evidence": "the specific evidence (payload, request, response) demonstrating the vulnerability"
}}"""
            }]
        )

        analysis = _parse_json(response.content[0].text)

        description = (
            f"Impact: {analysis['impact']}\n\n"
            f"CVSS Score: {analysis['cvss_score']}\n\n"
            f"Evidence: {analysis['evidence']}"
        )
        issue = await self._jira.create_issue(
            project_key=project_key,
            summary=analysis["report"],
            description=description,
            issue_type="Bug",
            labels=["security"],
        )

        return {
            "report": analysis["report"],
            "impact": analysis["impact"],
            "cvss_score": analysis["cvss_score"],
            "evidence": analysis["evidence"],
            "jira_id": issue["jira_id"],
            "url": issue["url"],
        }
