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
from sqlalchemy import select, func

from bot.config import config
from bot.models.db import Base
from bot.models.achievement import Achievement
from bot.models.booster import ActiveBooster
from bot.models.shop import ShopItem  # если используете отдельную модель, иначе в db.py
from bot.middlewares.throttle import ThrottlingMiddleware
from bot.handlers import start, game, profile, admin, shop, tournament, referral, achievements, settings
from bot.services.game_engine import GameEngine
from bot.services.scheduler import SchedulerService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные
bot: Bot = None
dp: Dispatcher = None
redis_client: redis.Redis = None
engine = None
async_session_maker = None
game_engine: GameEngine = None
scheduler: SchedulerService = None

async def create_tables():
    """Создание таблиц, если их нет."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created/verified")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")

async def init_achievements():
    """Инициализация начальных достижений."""
    async with async_session_maker() as session:
        count = await session.scalar(select(func.count(Achievement.id)))
        if count > 0:
            return
        achievements = [
            Achievement(name="Новичок", description="Сделать 10 ставок", condition_type="total_bets", condition_value=10, reward_stars=50, reward_exp=100, order=1),
            Achievement(name="Игрок", description="Сделать 100 ставок", condition_type="total_bets", condition_value=100, reward_stars=200, reward_exp=500, order=2),
            Achievement(name="Ветеран", description="Сделать 1000 ставок", condition_type="total_bets", condition_value=1000, reward_stars=1000, reward_exp=2000, order=3),
            Achievement(name="Победитель", description="Выиграть 50 раз", condition_type="total_wins", condition_value=50, reward_stars=300, reward_exp=600, order=4),
            Achievement(name="Чемпион", description="Выиграть 500 раз", condition_type="total_wins", condition_value=500, reward_stars=1500, reward_exp=3000, order=5),
            Achievement(name="Миллионер", description="Выиграть всего 10000 звёзд", condition_type="total_stars_won", condition_value=10000, reward_stars=2000, reward_exp=4000, order=6),
            Achievement(name="Лидер", description="Пригласить 5 друзей", condition_type="referrals_count", condition_value=5, reward_stars=500, reward_exp=1000, order=7),
            Achievement(name="Магнат", description="Пригласить 20 друзей", condition_type="referrals_count", condition_value=20, reward_stars=2000, reward_exp=5000, order=8),
            Achievement(name="Мастер уровня", description="Достичь 10 уровня", condition_type="level", condition_value=10, reward_stars=1000, reward_exp=2000, order=9),
        ]
        session.add_all(achievements)
        await session.commit()
        logger.info("Initial achievements created")

async def init_shop_items():
    """Инициализация товаров магазина (с новыми бустерами и кастомизацией)."""
    async with async_session_maker() as session:
        count = await session.scalar(select(func.count(ShopItem.id)))
        if count > 0:
            return
        items = [
            # Существующие
            ShopItem(name="Удвоитель удачи", description="Увеличивает шанс выигрыша на 10% в следующих 5 раундах.", price=500, item_type="booster", item_data={"boost": 1.1, "rounds": 5, "booster_type": "win_chance"}),
            ShopItem(name="Золотая звезда", description="Эксклюзивный скин для твоего профиля.", price=1000, item_type="skin", item_data={"skin": "gold"}),
            ShopItem(name="Страховка", description="При проигрыше в следующем раунде получаешь полный возврат ставки (однократно).", price=300, item_type="booster", item_data={"booster_type": "insurance", "uses": 1}),
            # Новые
            ShopItem(name="Удача +20%", description="Увеличивает шанс выигрыша на 20% в следующих 3 раундах.", price=800, item_type="booster", item_data={"boost": 1.2, "rounds": 3, "booster_type": "win_chance"}),
            ShopItem(name="Страховка (5 ставок)", description="В течение следующих 5 ставок, если проигрываешь, получаешь полный возврат.", price=1200, item_type="booster", item_data={"booster_type": "insurance", "uses": 5}),
            ShopItem(name="Эпический титул", description="Получи титул «Звёздный властелин» перед своим именем в чатах.", price=2000, item_type="title", item_data={"title": "✨ Звёздный властелин"}),
            ShopItem(name="Неоновый профиль", description="Твой профиль будет светиться в темноте (специальный скин).", price=1500, item_type="skin", item_data={"skin": "neon"}),
            ShopItem(name="Усилитель опыта x2", description="Удваивает получаемый опыт в течение 30 минут.", price=600, item_type="booster", item_data={"boost": 2.0, "duration_minutes": 30, "booster_type": "exp_boost"}),
        ]
        session.add_all(items)
        await session.commit()
        logger.info("Initial shop items created")

async def setup_bot_commands():
    """Установка команд бота."""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="game", description="Играть"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="achievements", description="Мои достижения"),
        BotCommand(command="shop", description="Магазин"),
        BotCommand(command="tournaments", description="Турниры"),
        BotCommand(command="referral", description="Реферальная система"),
        BotCommand(command="daily", description="Ежедневный бонус"),
        BotCommand(command="settings", description="Настройки"),
    ]
    await bot.set_my_commands(commands)

async def shutdown():
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
    
    redis_client = redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        encoding="utf-8"
    )
    
    engine = create_async_engine(
        config.DATABASE_URL,
        echo=False,
        pool_size=20,
        max_overflow=10
    )
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    await create_tables()
    await init_achievements()
    await init_shop_items()
    
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = RedisStorage(redis_client)
    dp = Dispatcher(storage=storage)
    
    dp.message.middleware(ThrottlingMiddleware())
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(game.router)
    dp.include_router(profile.router)
    dp.include_router(achievements.router)
    dp.include_router(shop.router)
    dp.include_router(tournament.router)
    dp.include_router(referral.router)
    dp.include_router(settings.router)
    dp.include_router(admin.router)
    
    await setup_bot_commands()
    
    game_engine = GameEngine(bot, redis_client, async_session_maker)
    scheduler = SchedulerService(bot, async_session_maker, redis_client)
    
    asyncio.create_task(game_engine.run())
    asyncio.create_task(scheduler.run())
    
    logger.info("Bot started")
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await shutdown()

if __name__ == "__main__":
    asyncio.run(main())
