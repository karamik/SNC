# api/core/security.py

import hmac
import hashlib
import urllib.parse
from typing import Dict, Any
from fastapi import Request, HTTPException

from api.core.config import settings

def verify_telegram_init_data(init_data: str) -> bool:
    """
    Проверяет подпись данных инициализации от Telegram Web App.
    Возвращает True, если данные подлинные.
    """
    # Парсим строку запроса в словарь
    parsed = urllib.parse.parse_qs(init_data)
    # Преобразуем значения из списков в строки (обычно они одноэлементные)
    data_check = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in parsed.items()}
    
    # Извлекаем хеш
    hash_received = data_check.pop('hash', None)
    if not hash_received:
        return False
    
    # Сортируем ключи и формируем строку для проверки
    items = []
    for key in sorted(data_check.keys()):
        value = data_check[key]
        if isinstance(value, list):
            value = value[0]  # если вдруг список
        items.append(f"{key}={value}")
    data_check_string = "\n".join(items)
    
    # Вычисляем HMAC-SHA256 секретного ключа (токен бота)
    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    return calculated_hash == hash_received

async def get_current_user_id(request: Request) -> int:
    """
    Получает telegram_id пользователя из запроса.
    Сначала проверяет заголовок X-Telegram-User-Id (для разработки),
    затем пытается извлечь из initData (для продакшена).
    """
    # Для разработки используем заголовок
    user_id = request.headers.get("X-Telegram-User-Id")
    if user_id:
        try:
            return int(user_id)
        except ValueError:
            pass
    
    # Попытка извлечь из initData (если передаётся в теле или в query)
    # В реальном проекте нужно получать initData из тела запроса или из query-параметра
    # Здесь упрощённо: будем считать, что initData приходит в заголовке X-Init-Data
    init_data = request.headers.get("X-Init-Data")
    if init_data and verify_telegram_init_data(init_data):
        # Парсим init_data и извлекаем user.id
        parsed = urllib.parse.parse_qs(init_data)
        user_data = parsed.get('user', [None])[0]
        if user_data:
            import json
            try:
                user_info = json.loads(user_data)
                return user_info['id']
            except:
                pass
    
    raise HTTPException(status_code=401, detail="Unauthorized")
