import os
from typing import List
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

class Config:
    # Токен бота
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    
    # База данных
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://star_user:star_password@db:5432/star_db")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    # API базовый URL
    API_BASE_URL: str = os.getenv("API_BASE_URL", "https://your-domain.com")
    
    # Секретный ключ
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-secret-key-change-me")
    
    # ID администраторов (список)
    ADMIN_IDS: List[int] = []
    
    # Ссылка для баннера
    BANNER_LINK: str = os.getenv("BANNER_LINK", "https://t.me/starsobot_bot?start=438850682")
    
    def __init__(self):
        # Парсим ADMIN_IDS
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        if admin_ids_str:
            try:
                self.ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]
            except ValueError:
                self.ADMIN_IDS = []
        
        # Проверяем обязательные поля
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не задан!")
        if not self.SECRET_KEY or self.SECRET_KEY == "default-secret-key-change-me":
            raise ValueError("SECRET_KEY должен быть изменён!")
        if "your-domain.com" in self.API_BASE_URL:
            print("⚠️ ВНИМАНИЕ: API_BASE_URL не изменён! Используйте реальный домен.")

# Создаём глобальный экземпляр конфигурации
config = Config()
