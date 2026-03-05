#!/usr/bin/env python3
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from bot.config import config
from bot.models.db import Base
from bot.middlewares.throttle import ThrottlingMiddleware
from bot.handlers import start, game, profile, admin, shop, tournament, referral
from bot.services.game_engine import GameEngine
from bot.services.scheduler import SchedulerService
import bot.services.daily_bonus as daily_bonus
import bot.services.tournament_manager as tournament_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные для доступа из других модулей
bot: Bot = None
dp: Dispatcher = None
redis_client: redis.Redis = None
engine = None
async_session_maker = None
game_engine: GameEngine = None
scheduler: SchedulerService = None

async def create_tables():
    """Создание таблиц, если их нет (только для разработки)"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created/verified")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")

async def setup_bot_commands():
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="game", description="Играть"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="shop", description="Магазин"),
        BotCommand(command="tournaments", description="Турниры"),
        BotCommand(command="referral", description="Реферальная система"),
        BotCommand(command="daily", description="Ежедневный бонус"),
    ]
    await bot.set_my_commands(commands)

async def shutdown():
    """Корректное завершение"""
    logger.info("Shutting down...")
    if game_engine:
        await game_engine.stop()
    if scheduler:
        await scheduler.stop()
    if redis_client:
        await redis_client.close()
    if engine:
        await engine.dispose()
    await bot.session.close()

async def main():
    global bot, dp, redis_client, engine, async_session_maker, game_engine, scheduler
    
    # Инициализация Redis
    redis_client = redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        encoding="utf-8"
    )
    
    # Инициализация базы данных
    engine = create_async_engine(
        config.DATABASE_URL,
        echo=False,
        pool_size=20,
        max_overflow=10
    )
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    # Создание таблиц (можно убрать, если используете миграции)
    await create_tables()
    
    # Инициализация бота и диспетчера
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = RedisStorage(redis_client)
    dp = Dispatcher(storage=storage)
    
    # Middleware
    dp.message.middleware(ThrottlingMiddleware())
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(game.router)
    dp.include_router(profile.router)
    dp.include_router(shop.router)
    dp.include_router(tournament.router)
    dp.include_router(referral.router)
    dp.include_router(admin.router)  # админ-панель
    
    # Установка команд
    await setup_bot_commands()
    
    # Запуск фоновых сервисов
    game_engine = GameEngine(bot, redis_client, async_session_maker)
    scheduler = SchedulerService(bot, async_session_maker, redis_client)
    
    # Запускаем игровой движок (минутные раунды)
    asyncio.create_task(game_engine.run())
    
    # Запускаем планировщик (ежедневные бонусы, турниры и т.д.)
    asyncio.create_task(scheduler.run())
    
    logger.info("Bot started")
    
    try:
        # Запуск поллинга
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await shutdown()

if __name__ == "__main__":
    asyncio.run(main())
