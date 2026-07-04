from fastapi import APIRouter, WebSocket
from .realtime_proxy import handle_realtime_session

router = APIRouter()

@router.websocket("/ws/realtime")
async def realtime_endpoint(websocket: WebSocket):
    await handle_realtime_session(websocket)
