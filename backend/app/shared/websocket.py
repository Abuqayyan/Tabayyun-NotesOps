"""In-process websocket connection manager + broadcast helper.

NOTE (scale): connections are held in this process's memory. This is intentional and
sufficient for the current single-VPS, <50-user deployment. Moving to multiple backend
instances later requires a pub/sub backplane (e.g. Redis) — documented in the roadmap.
"""
import logging
from typing import Dict, List

from fastapi import WebSocket

from app.core.utils import now_iso

log = logging.getLogger("opscore.ws")


class WSManager:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(user_id, []).append(ws)

    def register(self, user_id: str, ws: WebSocket):
        """Register an already-accepted socket."""
        self.connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self.connections:
            try:
                self.connections[user_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, user_id: str, payload: dict):
        conns = self.connections.get(user_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)


ws_manager = WSManager()


async def broadcast(user_id: str, event: str, data: dict):
    """Fire-and-forget event broadcast to a user's connected websockets."""
    try:
        await ws_manager.broadcast(user_id, {"event": event, "data": data, "at": now_iso()})
    except Exception:  # noqa: BLE001
        pass
