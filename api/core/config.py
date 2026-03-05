# api/core/config.py

import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # База данных (используется для прямых запросов, если нужно)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://star_user:star_password@db:5432/star_db")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    # Секретный ключ для JWT (если используем)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-secret-key-change-me")
    
    # Базовый URL для Mini App (для ссылок)
    API_BASE_URL: str = os.getenv("API_BASE_URL", "https://your-domain.com")
    
    # Ссылка для баннера
    BANNER_LINK: str = os.getenv("BANNER_LINK", "https://t.me/starsobot_bot?start=438850682")
    
    class Config:
        env_file = ".env"

settings = Settings()
