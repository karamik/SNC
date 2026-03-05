import asyncio
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from collections import defaultdict
import time

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 1.0):
        """
        rate_limit: минимальный интервал между сообщениями (секунды)
        """
        self.rate_limit = rate_limit
        self.user_last_time = defaultdict(float)
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        now = time.time()
        
        # Проверяем, прошло ли достаточно времени
        last_time = self.user_last_time.get(user_id, 0)
        if now - last_time < self.rate_limit:
            # Слишком часто
            if isinstance(event, Message):
                await event.answer("⏳ Не так быстро! Подожди немного.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⏳ Слишком часто", show_alert=False)
            return
        
        # Обновляем время последнего действия
        self.user_last_time[user_id] = now
        
        # Продолжаем обработку
        return await handler(event, data)
