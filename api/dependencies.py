# api/dependencies.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import redis.asyncio as redis
from api.core.config import settings

# Создаём движок базы данных
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10
)

# Фабрика сессий
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db() -> AsyncSession:
    """
    Зависимость для получения сессии базы данных.
    Используется в эндпоинтах FastAPI.
    """
    async with AsyncSessionLocal() as session:
        yield session

# Redis клиент (один на всё приложение)
redis_client = None

async def get_redis():
    """
    Зависимость для получения Redis клиента.
    """
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            encoding="utf-8"
        )
    return redis_client
