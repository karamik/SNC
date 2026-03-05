# api/main.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

from api.routers import game, user, admin
from api.core.config import settings

# Создаём приложение FastAPI
app = FastAPI(
    title="Star Doubler API",
    description="API для игры Звёздный удвоитель",
    version="1.0.0"
)

# Настройка CORS для разрешения запросов из Telegram Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене лучше ограничить доменами Telegram
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем статические файлы (фронтенд Mini App)
# Предполагается, что статика лежит в папке static
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Подключаем роутеры
app.include_router(game.router, prefix="/api/game", tags=["game"])
app.include_router(user.router, prefix="/api/user", tags=["user"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

@app.get("/")
async def root():
    return {"message": "Star Doubler API is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}
