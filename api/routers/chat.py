# api/routers/chat.py
import json
import logging
import urllib.parse
from typing import List, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from api.dependencies import get_db
from bot.models.chat import ChatMessage
from bot.models.db import User
from api.core.security import verify_telegram_init_data

router = APIRouter()
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Активные соединения: room -> list of websocket
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Для каждого соединения храним user_id (чтобы знать, кто пишет)
        self.user_sessions: Dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, room: str, user_id: int):
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)
        self.user_sessions[websocket] = user_id
        logger.info(f"User {user_id} connected to room {room}")

    def disconnect(self, websocket: WebSocket, room: str):
        if room in self.active_connections:
            if websocket in self.active_connections[room]:
                self.active_connections[room].remove(websocket)
        if websocket in self.user_sessions:
            del self.user_sessions[websocket]
        logger.info(f"WebSocket disconnected from room {room}")

    async def broadcast(self, message: str, room: str):
        if room in self.active_connections:
            for connection in self.active_connections[room]:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {room}: {e}")

manager = ConnectionManager()

async def get_user_from_init_data(init_data: str, db: AsyncSession):
    """Проверяет init_data и возвращает пользователя."""
    if not verify_telegram_init_data(init_data):
        logger.warning("Invalid init_data signature")
        return None
    # Парсим init_data для извлечения user
    parsed = urllib.parse.parse_qs(init_data)
    user_data = parsed.get('user', [None])[0]
    if not user_data:
        logger.warning("No user data in init_data")
        return None
    try:
        user_info = json.loads(user_data)
        telegram_id = user_info['id']
        # Ищем пользователя в БД по telegram_id
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(f"User with telegram_id {telegram_id} not found")
            return None
        return user
    except Exception as e:
        logger.exception(f"Error parsing user data: {e}")
        return None

@router.websocket("/ws/{room}")
async def websocket_endpoint(
    websocket: WebSocket,
    room: str,
    init_data: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint для чата.
    - room: комната (например, 'general')
    - init_data: строка initData от Telegram Web App
    """
    # Аутентификация
    user = await get_user_from_init_data(init_data, db)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await manager.connect(websocket, room, user.id)

    # Отправляем последние 50 сообщений из БД
    messages = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.room == room)
        .order_by(desc(ChatMessage.created_at))
        .limit(50)
    )
    messages = messages.scalars().all()
    history = [
        {
            "username": msg.username or f"User {msg.user_id}",
            "message": msg.message,
            "time": msg.created_at.isoformat()
        }
        for msg in reversed(messages)  # в хронологическом порядке
    ]
    await websocket.send_text(json.dumps({"type": "history", "data": history}))

    try:
        while True:
            # Получаем сообщение от клиента
            data = await websocket.receive_text()
            try:
                msg_data = json.loads(data)
                message_text = msg_data.get("message", "")
            except:
                message_text = data

            # Сохраняем в БД
            chat_message = ChatMessage(
                user_id=user.id,
                username=user.username or user.first_name or f"User {user.id}",
                message=message_text,
                room=room
            )
            db.add(chat_message)
            await db.commit()

            # Формируем сообщение для рассылки
            broadcast_msg = json.dumps({
                "type": "message",
                "data": {
                    "username": chat_message.username,
                    "message": message_text,
                    "time": chat_message.created_at.isoformat()
                }
            })
            await manager.broadcast(broadcast_msg, room)

    except WebSocketDisconnect:
        manager.disconnect(websocket, room)
        await manager.broadcast(json.dumps({
            "type": "system",
            "data": f"{user.username or 'Кто-то'} покинул чат"
        }), room)
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        manager.disconnect(websocket, room)
