from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt
from app.config import settings
from app.agents.orchestrator import QAOrchestrator

router = APIRouter()
orchestrator = QAOrchestrator()


def verify_ws_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
):
    email = verify_ws_token(token)
    if not email:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") != "user_message":
                continue

            content = data.get("content", "")
            project_id = data.get("project_id", "")

            async for event in orchestrator.process(content, session_id, project_id):
                await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
