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
