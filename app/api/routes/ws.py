"""WebSocket endpoint and message routing."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.domain.models import InitPayload, WsEvent, WsEventType

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    store = websocket.app.state.store
    manager = websocket.app.state.ws_manager

    await manager.connect(websocket)
    try:
        flows = await store.list_flows(limit=200)
        queue = await store.queue_state()
        config = await store.get_config()
        init = InitPayload(config=config, queue=queue, flows=flows)
        await manager.send_personal(websocket, WsEvent(event=WsEventType.INIT, data=init.model_dump(mode="json")))

        while True:
            message = await websocket.receive_json()
            event = message.get("event")
            if event == "pong":
                await manager.mark_pong(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)

