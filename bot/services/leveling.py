# bot/services/leveling.py

import math
from sqlalchemy.ext.asyncio import AsyncSession
from bot.models.db import User

# Формула опыта для следующего уровня: базовое значение * уровень^коэффициент
BASE_EXP = 100
EXP_FACTOR = 1.5

def exp_for_next_level(level: int) -> int:
    """Возвращает количество опыта, необходимое для перехода с level на level+1."""
    return int(BASE_EXP * (level ** EXP_FACTOR))

def exp_for_level(level: int) -> int:
    """Возвращает общее количество опыта, необходимое для достижения уровня level (начиная с 1)."""
    if level <= 1:
        return 0
    total = 0
    for i in range(1, level):
        total += exp_for_next_level(i)
    return total

def calculate_level(exp: int) -> int:
    """Вычисляет уровень по текущему опыту."""
    level = 1
    while exp >= exp_for_next_level(level):
        exp -= exp_for_next_level(level)
        level += 1
    return level

async def update_user_level(user: User, session: AsyncSession) -> bool:
    """
    Проверяет, не пора ли повысить уровень пользователю на основе его опыта.
    Возвращает True, если уровень повысился.
    """
    new_level = calculate_level(user.exp)
    if new_level > user.level:
        old_level = user.level
        user.level = new_level
        # Можно добавить бонус за повышение уровня (например, немного звёзд)
        level_up_bonus = new_level * 10  # пример
        user.balance += level_up_bonus
        # Здесь можно также создать транзакцию для бонуса, но для простоты опустим
        await session.commit()
        return True
    return False

def add_exp(user: User, amount: int) -> int:
    """
    Добавляет опыт пользователю (без сохранения в БД).
    Возвращает новый уровень (если изменился, иначе старый).
    """
    old_level = user.level
    user.exp += amount
    new_level = calculate_level(user.exp)
    if new_level > old_level:
        user.level = new_level
        # Бонус за уровень может быть начислен отдельно
    return new_level
