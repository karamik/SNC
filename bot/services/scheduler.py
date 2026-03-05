# bot/services/scheduler.py

import asyncio
import datetime
import logging
from typing import Callable, Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker
import redis.asyncio as redis

from bot.services import daily_bonus
from bot.services import tournament_manager

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self, bot: Bot, session_maker: async_sessionmaker, redis_client: redis.Redis):
        self.bot = bot
        self.session_maker = session_maker
        self.redis = redis_client
        self.running = True
        self.tasks = []

    async def run(self):
        """Запуск планировщика."""
        logger.info("Scheduler service started")
        # Запускаем все задачи
        self.tasks = [
            asyncio.create_task(self.daily_bonus_task()),
            asyncio.create_task(self.tournament_update_task()),
            asyncio.create_task(self.cleanup_task()),
        ]
        # Ждём завершения (никогда не завершаются)
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def stop(self):
        """Остановка планировщика."""
        self.running = False
        for task in self.tasks:
            task.cancel()
        logger.info("Scheduler service stopped")

    async def daily_bonus_task(self):
        """Задача ежедневного бонуса: запускается каждый день в 00:05 UTC."""
        while self.running:
            now = datetime.datetime.utcnow()
            # Вычисляем время до следующего запуска в 00:05
            target = now.replace(hour=0, minute=5, second=0, microsecond=0)
            if now >= target:
                target += datetime.timedelta(days=1)
            sleep_seconds = (target - now).total_seconds()
            await asyncio.sleep(sleep_seconds)

            if not self.running:
                break

            logger.info("Running daily bonus task")
            try:
                await daily_bonus.process_daily_bonuses(self.session_maker, self.bot)
            except Exception as e:
                logger.exception(f"Error in daily bonus task: {e}")

    async def tournament_update_task(self):
        """Обновление турниров: проверка каждые 5 минут."""
        while self.running:
            await asyncio.sleep(300)  # 5 минут
            if not self.running:
                break
            try:
                await tournament_manager.update_tournaments(self.session_maker, self.bot)
            except Exception as e:
                logger.exception(f"Error in tournament update task: {e}")

    async def cleanup_task(self):
        """Очистка старых данных (например, удаление старых записей из Redis, логов). Раз в час."""
        while self.running:
            await asyncio.sleep(3600)  # 1 час
            if not self.running:
                break
            try:
                # Очистка старых ключей раундов (в Redis уже есть expire, но можно дополнительно)
                # Например, удаляем ключи раундов старше 1 дня
                now = datetime.datetime.utcnow()
                day_ago = int((now - datetime.timedelta(days=1)).timestamp())
                # Не реализуем пока, но можно добавить при необходимости
                pass
            except Exception as e:
                logger.exception(f"Error in cleanup task: {e}")
