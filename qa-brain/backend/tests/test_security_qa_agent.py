import pytest
import json
from unittest.mock import AsyncMock, patch
from app.agents.security_qa import SecurityQAAgent

MOCK_STORY = {
    "jira_id": "SCRUM-300",
    "title": "User can upload a profile picture",
    "description": "As a user I want to upload a profile picture so my account feels personal",
    "acceptance_criteria": "Given an image file under 5MB, when I upload it, then it becomes my avatar",
    "status": "In Progress",
}

MOCK_OWASP_TEST_CASES = [
    {
        "title": "Reject oversized file upload",
        "type": "security",
        "owasp_category": "A04:2021-Insecure Design",
        "steps": ["Step 1: Attempt to upload a 50MB file", "Step 2: Submit"],
        "expected_result": "Upload is rejected with a clear size-limit error",
        "priority": "high",
    },
]

MOCK_OWASP_MAPPING = [
    {
        "owasp_category": "A01:2021-Broken Access Control",
        "status": "gap",
        "risk_level": "high",
        "notes": "No check that the uploader owns the profile being modified",
    },
    {
        "owasp_category": "A04:2021-Insecure Design",
        "status": "covered",
        "risk_level": "medium",
        "notes": "File size and type are validated before upload",
    },
]

MOCK_RBAC_MATRIX = {
    "roles": ["admin", "member", "guest"],
    "matrix": [
        {
            "boundary": "Delete another user's project",
            "access": {"admin": "allow", "member": "deny", "guest": "deny"},
        },
        {
            "boundary": "View own project settings",
            "access": {"admin": "allow", "member": "allow", "guest": "deny"},
        },
    ],
}

SAMPLE_OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Sample API", "version": "1.0.0"},
    "paths": {
        "/users/{id}": {
            "get": {"summary": "Get user", "parameters": [{"name": "id", "in": "path"}], "responses": {"200": {"description": "OK"}}},
            "delete": {"summary": "Delete user", "parameters": [{"name": "id", "in": "path"}], "responses": {"204": {"description": "No Content"}}},
        }
    },
}

MOCK_API_SECURITY_CHECKLIST = {
    "broken_access": ["Verify /users/{id} DELETE checks the caller owns or administers the target user"],
    "injection": ["Verify {id} path parameter is validated as a UUID/int before use in queries"],
    "auth": ["Verify /users/{id} endpoints require an authenticated session"],
}


@pytest.mark.asyncio
async def test_generate_owasp_test_cases_returns_list():
    async def fake_call_qwen(prompt_content, max_tokens=500):
        if MOCK_OWASP_TEST_CASES[0]["owasp_category"] in prompt_content:
            return json.dumps(MOCK_OWASP_TEST_CASES[0])
        return json.dumps({"not_applicable": True})

    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", side_effect=fake_call_qwen):
            result = await agent.generate_owasp_test_cases("SCRUM-300")

    assert len(result) == 1
    assert result[0]["owasp_category"] == "A04:2021-Insecure Design"
    assert result[0]["type"] == "security"


@pytest.mark.asyncio
async def test_generate_owasp_test_cases_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_qwen", True):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.generate_owasp_test_cases("SCRUM-300")

    assert len(result) >= 1
    assert result[0]["title"].startswith("[MOCK]")
    assert result[0]["type"] == "security"


@pytest.mark.asyncio
async def test_generate_owasp_test_cases_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.generate_owasp_test_cases("SCRUM-300")

    assert result[0]["title"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_generate_owasp_test_cases_falls_back_per_category_on_partial_qwen_failure():
    async def flaky_call_qwen(prompt_content, max_tokens=500):
        if "A03:2021-Injection" in prompt_content:
            raise Exception("timed out")
        if "A01:2021-Broken Access Control" in prompt_content:
            return json.dumps({
                "title": "Real IDOR test case",
                "type": "security",
                "owasp_category": "A01:2021-Broken Access Control",
                "steps": ["Step 1"],
                "expected_result": "denied",
                "priority": "high",
            })
        return json.dumps({"not_applicable": True})

    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", side_effect=flaky_call_qwen):
            result = await agent.generate_owasp_test_cases("SCRUM-300")

    by_category = {tc["owasp_category"]: tc for tc in result}
    assert by_category["A01:2021-Broken Access Control"]["title"] == "Real IDOR test case"
    assert by_category["A03:2021-Injection"]["title"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_map_story_to_owasp_returns_list_of_findings():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_OWASP_MAPPING)):
            result = await agent.map_story_to_owasp("SCRUM-300")

    assert len(result) == 2
    assert result[0]["owasp_category"] == "A01:2021-Broken Access Control"
    assert result[0]["status"] == "gap"
    assert result[0]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_map_story_to_owasp_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_qwen", True):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.map_story_to_owasp("SCRUM-300")

    assert len(result) >= 1
    assert result[0]["notes"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_map_story_to_owasp_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.map_story_to_owasp("SCRUM-300")

    assert result[0]["notes"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_generate_rbac_matrix_returns_matrix():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_RBAC_MATRIX)):
            result = await agent.generate_rbac_matrix(
                roles=["admin", "member", "guest"],
                feature_description="Project settings page with delete and view actions",
            )

    assert result["roles"] == ["admin", "member", "guest"]
    assert len(result["matrix"]) == 2
    assert result["matrix"][0]["access"]["admin"] == "allow"


@pytest.mark.asyncio
async def test_generate_rbac_matrix_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_qwen", True):
        agent = SecurityQAAgent()
        result = await agent.generate_rbac_matrix(
            roles=["admin", "member"],
            feature_description="Billing page",
        )

    assert result["roles"] == ["admin", "member"]
    assert len(result["matrix"]) >= 1
    assert result["matrix"][0]["boundary"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_generate_rbac_matrix_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.generate_rbac_matrix(
                roles=["admin", "member"],
                feature_description="Billing page",
            )

    assert result["matrix"][0]["boundary"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_generate_api_security_checklist_returns_checklist():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent._openapi, "parse_spec", new_callable=AsyncMock, return_value=SAMPLE_OPENAPI_SPEC), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_API_SECURITY_CHECKLIST)):
            result = await agent.generate_api_security_checklist("https://example.com/openapi.json")

    assert "broken_access" in result
    assert "injection" in result
    assert "auth" in result
    assert len(result["broken_access"]) == 1


@pytest.mark.asyncio
async def test_generate_api_security_checklist_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_qwen", True):
        agent = SecurityQAAgent()
        with patch.object(agent._openapi, "parse_spec", new_callable=AsyncMock, return_value=SAMPLE_OPENAPI_SPEC):
            result = await agent.generate_api_security_checklist("https://example.com/openapi.json")

    assert result["broken_access"][0].startswith("[MOCK]")
    assert "injection" in result
    assert "auth" in result


@pytest.mark.asyncio
async def test_generate_api_security_checklist_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent._openapi, "parse_spec", new_callable=AsyncMock, return_value=SAMPLE_OPENAPI_SPEC), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.generate_api_security_checklist("https://example.com/openapi.json")

    assert result["broken_access"][0].startswith("[MOCK]")


MOCK_SCAN_JSON = json.dumps({
    "alerts": [
        {"name": "SQL Injection", "risk": "High", "url": "https://app.example.com/login"},
        {"name": "Missing X-Frame-Options Header", "risk": "Low", "url": "https://app.example.com/"},
    ]
})

MOCK_TRIAGE_RESULT = {
    "prioritized": [
        {"finding": "SQL Injection at /login", "severity": "critical", "cvss_estimate": 9.8},
    ],
    "false_positives": ["Missing X-Frame-Options Header — mitigated by CSP frame-ancestors"],
}

MOCK_DEFECT_ANALYSIS = {
    "report": "SQL Injection vulnerability in the login form's email field",
    "impact": "An unauthenticated attacker can bypass authentication or exfiltrate the user database",
    "cvss_score": 9.8,
    "evidence": "Payload `' OR 1=1 --` in the email field returned an authenticated session",
}

MOCK_CREATE_ISSUE_RESULT = {"jira_id": "SCRUM-501", "url": "https://example.atlassian.net/browse/SCRUM-501"}


@pytest.mark.asyncio
async def test_triage_vulnerabilities_returns_prioritized_and_false_positives():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_TRIAGE_RESULT)):
            result = await agent.triage_vulnerabilities(MOCK_SCAN_JSON)

    assert len(result["prioritized"]) == 1
    assert result["prioritized"][0]["severity"] == "critical"
    assert len(result["false_positives"]) == 1


@pytest.mark.asyncio
async def test_triage_vulnerabilities_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_qwen", True):
        agent = SecurityQAAgent()
        result = await agent.triage_vulnerabilities(MOCK_SCAN_JSON)

    assert len(result["prioritized"]) >= 1
    assert result["prioritized"][0]["finding"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_triage_vulnerabilities_falls_back_to_mock_when_qwen_fails():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.triage_vulnerabilities(MOCK_SCAN_JSON)

    assert result["prioritized"][0]["finding"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_write_security_defect_creates_real_jira_ticket_when_not_mock():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_DEFECT_ANALYSIS)), \
             patch.object(agent._jira, "create_issue", new_callable=AsyncMock, return_value=MOCK_CREATE_ISSUE_RESULT) as mock_create_issue:
            result = await agent.write_security_defect(
                "SQL injection found in login form email field, payload ' OR 1=1 --",
                project_key="SCRUM",
            )

    mock_create_issue.assert_called_once()
    assert result["jira_id"] == "SCRUM-501"
    assert result["url"] == "https://example.atlassian.net/browse/SCRUM-501"
    assert result["cvss_score"] == 9.8
    assert "report" in result
    assert "impact" in result
    assert "evidence" in result


@pytest.mark.asyncio
async def test_write_security_defect_mock_mode_does_not_call_create_issue():
    with patch("app.agents.security_qa.settings.mock_qwen", True):
        agent = SecurityQAAgent()
        with patch.object(agent._jira, "create_issue", new_callable=AsyncMock) as mock_create_issue:
            result = await agent.write_security_defect(
                "SQL injection found in login form email field, payload ' OR 1=1 --",
                project_key="SCRUM",
            )

    mock_create_issue.assert_not_called()
    assert result["jira_id"].startswith("[MOCK]")
    assert result["url"] == "[MOCK]"
    assert "report" in result
    assert "cvss_score" in result


@pytest.mark.asyncio
async def test_write_security_defect_falls_back_to_mock_without_creating_issue_when_qwen_fails():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        with patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")), \
             patch.object(agent._jira, "create_issue", new_callable=AsyncMock) as mock_create_issue:
            result = await agent.write_security_defect(
                "SQL injection found in login form email field, payload ' OR 1=1 --",
                project_key="SCRUM",
            )

    mock_create_issue.assert_not_called()
    assert result["jira_id"].startswith("[MOCK]")


MOCK_SPRINT_STORIES = [
    {"jira_id": "SCRUM-300", "title": "User can upload a profile picture", "description": "...", "status": "Done"},
    {"jira_id": "SCRUM-301", "title": "Admin can delete any user", "description": "...", "status": "Done"},
]

MOCK_DASHBOARD_SUMMARY = {
    "summary": "Access control coverage is strong, but injection testing is inconsistent across stories in this sprint.",
}


@pytest.mark.asyncio
async def test_build_owasp_dashboard_returns_coverage_and_summary():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        mock_mapping_300 = [
            {"owasp_category": "A01:2021-Broken Access Control", "status": "covered", "risk_level": "low", "notes": "ok"},
            {"owasp_category": "A03:2021-Injection", "status": "gap", "risk_level": "high", "notes": "no validation"},
        ]
        mock_mapping_301 = [
            {"owasp_category": "A01:2021-Broken Access Control", "status": "covered", "risk_level": "low", "notes": "ok"},
        ]
        with patch.object(agent._jira, "get_sprint_stories", new_callable=AsyncMock, return_value=MOCK_SPRINT_STORIES), \
             patch.object(agent, "map_story_to_owasp", new_callable=AsyncMock, side_effect=[mock_mapping_300, mock_mapping_301]), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, return_value=json.dumps(MOCK_DASHBOARD_SUMMARY)):
            result = await agent.build_owasp_dashboard("SPRINT-5")

    assert result["sprint_id"] == "SPRINT-5"
    assert result["coverage_by_category"]["A01:2021-Broken Access Control"] == 100
    assert result["coverage_by_category"]["A03:2021-Injection"] == 0
    assert "summary" in result


@pytest.mark.asyncio
async def test_build_owasp_dashboard_mock_mode_returns_mock_fixture():
    with patch("app.agents.security_qa.settings.mock_qwen", True):
        agent = SecurityQAAgent()
        result = await agent.build_owasp_dashboard("SPRINT-5")

    assert result["sprint_id"] == "SPRINT-5"
    assert "coverage_by_category" in result
    assert result["summary"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_build_owasp_dashboard_falls_back_to_mock_summary_but_keeps_real_coverage_when_qwen_fails():
    with patch("app.agents.security_qa.settings.mock_qwen", False):
        agent = SecurityQAAgent()
        mock_mapping_300 = [
            {"owasp_category": "A01:2021-Broken Access Control", "status": "covered", "risk_level": "low", "notes": "ok"},
        ]
        mock_mapping_301 = [
            {"owasp_category": "A01:2021-Broken Access Control", "status": "gap", "risk_level": "high", "notes": "no check"},
        ]
        with patch.object(agent._jira, "get_sprint_stories", new_callable=AsyncMock, return_value=MOCK_SPRINT_STORIES), \
             patch.object(agent, "map_story_to_owasp", new_callable=AsyncMock, side_effect=[mock_mapping_300, mock_mapping_301]), \
             patch.object(agent, "_call_qwen", new_callable=AsyncMock, side_effect=Exception("timed out")):
            result = await agent.build_owasp_dashboard("SPRINT-5")

    assert result["sprint_id"] == "SPRINT-5"
    assert result["coverage_by_category"]["A01:2021-Broken Access Control"] == 50
    assert result["summary"].startswith("[MOCK]")
