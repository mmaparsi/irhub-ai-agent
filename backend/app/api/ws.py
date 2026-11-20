from __future__ import annotations

import asyncio
import queue
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.auth.rbac import task_visible
from app.auth.security import decode_access_token
from app.database import open_session
from app.models import ActivityEvent, AgentTask, TaskEvent, User
from app.realtime import hub

router = APIRouter(tags=["realtime"])


class Principal:
    def __init__(self, user_id: str, role: str) -> None:
        self.id = user_id
        self.role = role


def _token(websocket: WebSocket) -> str:
    query = websocket.query_params.get("token") or ""
    if query:
        return query
    header = websocket.headers.get("sec-websocket-protocol") or ""
    for part in header.split(","):
        item = part.strip()
        if item.lower().startswith("bearer."):
            return item.split(".", 1)[1].strip()
        if item.count(".") >= 2:
            return item
    return ""


def _principal(token: str) -> Principal | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except Exception:
        return None
    db = open_session()
    try:
        user = db.get(User, payload.get("sub"))
        if user is None or not user.is_active:
            return None
        return Principal(user.id, user.role)
    finally:
        db.close()


def _stamp(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[no-any-return]
    return value


async def _pull(inbox: queue.Queue) -> dict[str, Any] | None:
    while True:
        try:
            return inbox.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.05)


def _activity_visible(user: Principal, event: dict[str, Any]) -> bool:
    if user.role == "admin":
        return True
    if event.get("user_id") and event.get("user_id") == user.id:
        return True
    return bool(event.get("role")) and event.get("role") == user.role


@router.websocket("/ws")
async def live_socket(websocket: WebSocket) -> None:
    user = _principal(_token(websocket))
    if user is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    inbox = hub.subscribe()
    tasks: set[str] = set()
    inbox_on = False
    seen: set[tuple] = set()
    try:
        receiver = asyncio.create_task(websocket.receive_json())
        while True:
            notice = asyncio.create_task(_pull(inbox))
            done, _pending = await asyncio.wait(
                {receiver, notice}, return_when=asyncio.FIRST_COMPLETED
            )
            if receiver in done:
                notice.cancel()
                try:
                    message = receiver.result()
                except WebSocketDisconnect:
                    return
                await _client(websocket, user, message, tasks, seen)
                if message.get("action") == "inbox":
                    inbox_on = True
                receiver = asyncio.create_task(websocket.receive_json())
                continue
            event = notice.result()
            if not event:
                continue
            if event.get("type") == "task" and event.get("task_id") in tasks:
                await _send(websocket, event, seen)
            elif event.get("type") == "activity" and inbox_on and _activity_visible(user, event):
                await _send(websocket, event, seen)
    except WebSocketDisconnect:
        return
    finally:
        hub.unsubscribe(inbox)


async def _send(websocket: WebSocket, event: dict[str, Any], seen: set[tuple]) -> None:
    key = (event.get("type"), event.get("task_id"), event.get("seq"), event.get("kind"))
    if key in seen:
        return
    seen.add(key)
    await websocket.send_json(event)


async def _client(
    websocket: WebSocket,
    user: Principal,
    message: dict[str, Any],
    tasks: set[str],
    seen: set[tuple],
) -> None:
    action = message.get("action")
    db = open_session()
    try:
        if action == "subscribe":
            task_id = str(message.get("task_id") or "")
            task = db.get(AgentTask, task_id)
            principal = db.get(User, user.id)
            if task is None or principal is None or not task_visible(db, principal, task):
                await websocket.send_json({"type": "error", "detail": "وظیفه در دسترس نیست"})
                return
            tasks.add(task_id)
            after = int(message.get("after_seq") or 0)
            rows = db.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id, TaskEvent.seq > after)
                .order_by(TaskEvent.seq)
            ).all()
            last = after
            for row in rows:
                last = row.seq
                await _send(
                    websocket,
                    {
                        "type": "task",
                        "task_id": task_id,
                        "seq": row.seq,
                        "kind": row.kind,
                        "payload": row.payload,
                        "id": row.id,
                        "created_at": _stamp(row.created_at),
                    },
                    seen,
                )
            await websocket.send_json({"type": "subscribed", "task_id": task_id, "last_seq": last})
        elif action == "inbox":
            after = int(message.get("after_seq") or 0)
            rows = db.scalars(
                select(ActivityEvent).where(ActivityEvent.seq > after).order_by(ActivityEvent.seq)
            ).all()
            last = after
            for row in rows:
                event = {
                    "type": "activity",
                    "seq": row.seq,
                    "kind": row.kind,
                    "payload": row.payload,
                    "user_id": row.user_id,
                    "role": row.role,
                    "task_id": row.task_id,
                    "created_at": _stamp(row.created_at),
                }
                if _activity_visible(user, event):
                    last = row.seq
                    await _send(websocket, event, seen)
            await websocket.send_json({"type": "inbox", "last_seq": last})
        elif action == "ping":
            await websocket.send_json({"type": "pong"})
    finally:
        db.close()
