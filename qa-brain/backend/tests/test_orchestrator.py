import pytest
from unittest.mock import AsyncMock, patch
from app.agents.orchestrator import QAOrchestrator

MOCK_TEST_CASES = [
    {"title": "Valid login", "type": "functional", "steps": ["Login"], "expected_result": "Success", "priority": "high"},
]

MOCK_ANALYSIS = {"ambiguities": ["What if email not found?"], "missing_requirements": ["Reset flow"], "risk_areas": ["Auth"]}


@pytest.mark.asyncio
async def test_process_generates_test_cases_on_story_request():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._manual_qa, "generate_test_cases", new_callable=AsyncMock, return_value=MOCK_TEST_CASES):
        async for event in orchestrator.process(
            message="Generate test cases for PROJ-123",
            session_id="test-session",
            project_id="proj-001"
        ):
            events.append(event)

    event_types = [e["type"] for e in events]
    assert "agent_start" in event_types
    assert "orchestrator_done" in event_types

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert "test_cases" in done_event.get("data", {})


@pytest.mark.asyncio
async def test_process_analyzes_story_on_analyze_request():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._manual_qa, "analyze_story", new_callable=AsyncMock, return_value=MOCK_ANALYSIS):
        async for event in orchestrator.process(
            message="Analyze story PROJ-123 for missing requirements",
            session_id="test-session",
            project_id="proj-001"
        ):
            events.append(event)

    done_event = next((e for e in events if e["type"] == "orchestrator_done"), None)
    assert done_event is not None
    assert "analysis" in done_event.get("data", {})


@pytest.mark.asyncio
async def test_process_generates_script_on_automation_request():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "generate_script_from_spec", new_callable=AsyncMock,
                       return_value={"framework": "playwright", "content": "test('x', async () => {});"}):
        async for event in orchestrator.process(
            message="Generate playwright script for PROJ-123",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["script"]["framework"] == "playwright"


@pytest.mark.asyncio
async def test_process_still_routes_bare_generate_to_manual_qa():
    """Collision guard: a message containing 'generate' must still route to
    generate_test_cases when it isn't specifically about automation scripts."""
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._manual_qa, "generate_test_cases", new_callable=AsyncMock,
                       return_value=MOCK_TEST_CASES):
        async for event in orchestrator.process(
            message="generate test cases for PROJ-123",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert "test_cases" in done_event["data"]


@pytest.mark.asyncio
async def test_process_classifies_ci_failure_from_run_url():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "classify_failure", new_callable=AsyncMock,
                       return_value={"root_cause": "Script", "explanation": "stale locator", "failed_step": "click submit"}):
        async for event in orchestrator.process(
            message="why did this fail? https://github.com/acme/repo/actions/runs/123456",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["classification"]["root_cause"] == "Script"


@pytest.mark.asyncio
async def test_process_returns_unknown_when_failure_message_has_no_run_url():
    orchestrator = QAOrchestrator()
    events = []

    async for event in orchestrator.process(
        message="why did this fail?",
        session_id="test-session",
        project_id="proj-001",
    ):
        events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert "message" in done_event["data"]


@pytest.mark.asyncio
async def test_process_suggests_self_healing_locator():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "suggest_self_healing", new_callable=AsyncMock,
                       return_value={"alternatives": ["getByTestId('submit')"], "strategy": "prefer test-id"}):
        async for event in orchestrator.process(
            message="this locator is broken: #submit-1, element not found at https://example.com/checkout",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["healing"]["alternatives"] == ["getByTestId('submit')"]


@pytest.mark.asyncio
async def test_process_generates_test_data():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "generate_test_data", new_callable=AsyncMock,
                       return_value=[{"label": "Valid boundary", "value": "x"}]):
        async for event in orchestrator.process(
            message="generate test data for the email field",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert len(done_event["data"]["test_data"]) == 1


@pytest.mark.asyncio
async def test_process_fixes_script():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "auto_fix_script", new_callable=AsyncMock,
                       return_value={"content": "fixed", "explanation": "why"}):
        async for event in orchestrator.process(
            message="auto fix this script:\n```\nbroken code\n```\nTimeoutError",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["fix"]["content"] == "fixed"


@pytest.mark.asyncio
async def test_process_applies_company_framework():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "apply_company_framework", new_callable=AsyncMock,
                       return_value={"content": "reformatted"}):
        async for event in orchestrator.process(
            message="apply company standard to this script:\n```\ntest('x', async () => {});\n```",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["formatted_script"]["content"] == "reformatted"


@pytest.mark.asyncio
async def test_process_maps_script_traceability():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "map_script_traceability", new_callable=AsyncMock,
                       return_value={"story_id": "PROJ-123", "covers_acceptance_criteria": True, "confidence": "high", "notes": "ok"}):
        async for event in orchestrator.process(
            message="map script traceability for PROJ-123:\n```\ntest('x', async () => {});\n```",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["traceability_mapping"]["story_id"] == "PROJ-123"


@pytest.mark.asyncio
async def test_process_generates_owasp_test_cases():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._security_qa, "generate_owasp_test_cases", new_callable=AsyncMock,
                       return_value=[{"title": "x", "type": "security", "owasp_category": "A03:2021-Injection", "steps": ["s"], "expected_result": "e", "priority": "high"}]):
        async for event in orchestrator.process(
            message="generate owasp test cases for PROJ-123",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert len(done_event["data"]["owasp_test_cases"]) == 1


@pytest.mark.asyncio
async def test_process_maps_story_to_owasp_and_not_traceability():
    """Collision guard: an OWASP-qualified 'map' message must route to
    map_story_to_owasp, not the generic traceability action."""
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._security_qa, "map_story_to_owasp", new_callable=AsyncMock,
                       return_value=[{"owasp_category": "A01:2021-Broken Access Control", "status": "gap", "risk_level": "high", "notes": "n"}]), \
         patch.object(orchestrator._manual_qa, "build_traceability_map", new_callable=AsyncMock) as mock_traceability:
        async for event in orchestrator.process(
            message="map story to owasp for PROJ-123",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    mock_traceability.assert_not_called()
    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert "owasp_mapping" in done_event["data"]
    assert done_event["data"]["owasp_mapping"][0]["owasp_category"] == "A01:2021-Broken Access Control"


@pytest.mark.asyncio
async def test_process_still_routes_bare_map_to_traceability():
    """Collision guard: a bare 'map' message with no OWASP qualifier must
    still route to the generic traceability action."""
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._manual_qa, "build_traceability_map", new_callable=AsyncMock,
                       return_value={"PROJ-123": ["Some test case"]}):
        async for event in orchestrator.process(
            message="map PROJ-123 to test cases",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert "traceability" in done_event["data"]


@pytest.mark.asyncio
async def test_process_generates_rbac_matrix():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._security_qa, "generate_rbac_matrix", new_callable=AsyncMock,
                       return_value={"roles": ["admin", "member"], "matrix": [{"boundary": "b", "access": {"admin": "allow", "member": "deny"}}]}):
        async for event in orchestrator.process(
            message="generate an rbac matrix for admin and member roles on the billing page",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["rbac_matrix"]["roles"] == ["admin", "member"]


@pytest.mark.asyncio
async def test_process_generates_api_security_checklist():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._security_qa, "generate_api_security_checklist", new_callable=AsyncMock,
                       return_value={"broken_access": ["a"], "injection": ["b"], "auth": ["c"]}):
        async for event in orchestrator.process(
            message="generate api security checklist for https://example.com/openapi.json",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["api_security_checklist"]["broken_access"] == ["a"]


@pytest.mark.asyncio
async def test_process_triages_vulnerabilities_from_pasted_json():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._security_qa, "triage_vulnerabilities", new_callable=AsyncMock,
                       return_value={"prioritized": [{"finding": "f", "severity": "high", "cvss_estimate": 7.0}], "false_positives": []}):
        async for event in orchestrator.process(
            message="triage vulnerabilities from this scanner result:\n```\n{\"alerts\": []}\n```",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["triage"]["prioritized"][0]["severity"] == "high"


@pytest.mark.asyncio
async def test_process_writes_security_defect():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._security_qa, "write_security_defect", new_callable=AsyncMock,
                       return_value={"report": "r", "impact": "i", "cvss_score": 9.0, "evidence": "e", "jira_id": "SCRUM-501", "url": "http://x"}):
        async for event in orchestrator.process(
            message="write a security defect with cvss score for this SQL injection finding",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["security_defect"]["jira_id"] == "SCRUM-501"


@pytest.mark.asyncio
async def test_process_builds_owasp_dashboard():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._security_qa, "build_owasp_dashboard", new_callable=AsyncMock,
                       return_value={"sprint_id": "SPRINT-5", "coverage_by_category": {"A01:2021-Broken Access Control": 100}, "summary": "s"}):
        async for event in orchestrator.process(
            message="show me the owasp dashboard for sprint 5",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["owasp_dashboard"]["sprint_id"] == "SPRINT-5"


@pytest.mark.asyncio
async def test_process_generates_script_from_api_spec_url():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "generate_script_from_spec", new_callable=AsyncMock,
                       return_value={"framework": "playwright", "content": "test('api', async () => {});"}) as mock_generate:
        async for event in orchestrator.process(
            message="Generate a playwright script from this openapi spec https://example.com/openapi.json",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["script"]["framework"] == "playwright"
    assert done_event["data"]["story_id"].startswith("API-SPEC-")
    mock_generate.assert_awaited_once()
    call_kwargs = mock_generate.await_args.kwargs
    assert call_kwargs["spec_url"] == "https://example.com/openapi.json"


@pytest.mark.asyncio
async def test_process_explores_and_generates_script_from_url():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "explore_and_generate", new_callable=AsyncMock,
                       return_value={"framework": "playwright", "content": "test('explored', async () => {});"}) as mock_explore:
        async for event in orchestrator.process(
            message="Explore https://staging.example.com and generate a script",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["script"]["framework"] == "playwright"
    assert done_event["data"]["story_id"].startswith("EXPLORED-")
    mock_explore.assert_awaited_once_with("https://staging.example.com", done_event["data"]["story_id"])


@pytest.mark.asyncio
async def test_process_explore_uses_story_id_from_message_when_present():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._automation_qa, "explore_and_generate", new_callable=AsyncMock,
                       return_value={"framework": "playwright", "content": "test('x', async () => {});"}):
        async for event in orchestrator.process(
            message="Explore https://staging.example.com for PROJ-500 and generate a script",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["story_id"] == "PROJ-500"
