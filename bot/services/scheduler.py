# bot/services/scheduler.py

import asyncio
import datetime
import logging
from typing import Callable, Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker
import redis.asyncio as redis
from sqlalchemy import select

from bot.models.db import User, Tournament
from bot.services import daily_bonus
from bot.services import tournament_manager
from bot.services.bank import process_completed_deposits

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
            asyncio.create_task(self.tournament_notification_task()),
            asyncio.create_task(self.deposit_check_task()),  # новая задача
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
                # Здесь можно добавить очистку старых ключей в Redis и т.п.
                pass
            except Exception as e:
                logger.exception(f"Error in cleanup task: {e}")

    async def tournament_notification_task(self):
        """Уведомления о скором начале турнира: каждые 15 минут."""
        while self.running:
            now = datetime.datetime.utcnow()
            soon = now + datetime.timedelta(minutes=45)
            later = now + datetime.timedelta(minutes=30)
            async with self.session_maker() as session:
                tournaments = await session.execute(
                    select(Tournament).where(
                        Tournament.start_time >= later,
                        Tournament.start_time <= soon,
                        Tournament.is_active == True
                    )
                )
                tournaments = tournaments.scalars().all()
                for t in tournaments:
                    users = await session.execute(
                        select(User).where(User.notifications_enabled == True)
                    )
                    users = users.scalars().all()
                    for user in users:
                        try:
                            await self.bot.send_message(
                                user.telegram_id,
                                f"⏳ <b>Скоро начнётся турнир!</b>\n\n"
                                f"«{t.name}» стартует в {t.start_time.strftime('%H:%M %d.%m')}\n"
                                f"Призовой фонд: {t.prize_pool} ⭐\n"
                                f"Минимальная ставка: {t.min_bet} ⭐\n"
                                f"Участвуй и побеждай!"
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify user {user.telegram_id}: {e}")
            await asyncio.sleep(900)  # 15 минут

    async def deposit_check_task(self):
        """Проверка завершённых депозитов (каждый час)."""
        while self.running:
            await asyncio.sleep(3600)  # 1 час
            if not self.running:
                break
            try:
                async with self.session_maker() as session:
                    count = await process_completed_deposits(session)
                    if count > 0:
                        logger.info(f"Processed {count} completed deposits")
            except Exception as e:
                logger.exception(f"Error in deposit check task: {e}")
