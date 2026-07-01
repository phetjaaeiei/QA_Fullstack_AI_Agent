import pytest
import json
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from app.main import app


@pytest.mark.asyncio
async def test_websocket_chat_returns_done_event(test_user, auth_token):
    mock_events = [
        {"type": "agent_start", "agent": "manual_qa", "message": "Processing..."},
        {"type": "orchestrator_done", "data": {"test_cases": []}},
    ]

    async def mock_process(*args, **kwargs):
        for event in mock_events:
            yield event

    with patch("app.api.chat.orchestrator.process", side_effect=mock_process):
        async with AsyncClient(transport=ASGIWebSocketTransport(app=app), base_url="ws://test") as client:
            async with aconnect_ws(
                f"ws://test/ws/chat/test-session?token={auth_token}",
                client
            ) as ws:
                await ws.send_json({"type": "user_message", "content": "Generate test cases for PROJ-123", "project_id": "proj-001"})
                events = []
                for _ in range(len(mock_events)):
                    msg = await ws.receive_json()
                    events.append(msg)

    event_types = [e["type"] for e in events]
    assert "agent_start" in event_types
    assert "orchestrator_done" in event_types
