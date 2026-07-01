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
