# bot/services/achievements.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.models.db import User
from bot.models.achievement import Achievement, UserAchievement
from bot.services.leveling import add_exp

logger = logging.getLogger(__name__)

async def check_achievements(user: User, session: AsyncSession):
    """
    Проверяет, выполнены ли условия для новых достижений пользователем,
    и выдает их (с наградой), если они еще не получены.
    Возвращает список новых полученных достижений.
    """
    # Получаем все достижения, которые пользователь уже получил
    achieved_result = await session.execute(
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)
    )
    achieved_ids = set(achieved_result.scalars().all())
    
    # Загружаем все доступные достижения
    all_achievements_result = await session.execute(
        select(Achievement).order_by(Achievement.order)
    )
    all_achievements = all_achievements_result.scalars().all()
    
    new_achievements = []
    for ach in all_achievements:
        if ach.id in achieved_ids:
            continue
        
        # Проверяем условие в зависимости от типа
        condition_met = False
        if ach.condition_type == 'total_bets':
            condition_met = user.total_bets >= ach.condition_value
        elif ach.condition_type == 'total_wins':
            condition_met = user.total_wins >= ach.condition_value
        elif ach.condition_type == 'total_stars_won':
            condition_met = user.total_stars_won >= ach.condition_value
        elif ach.condition_type == 'total_stars_bet':
            condition_met = user.total_stars_bet >= ach.condition_value
        elif ach.condition_type == 'referrals_count':
            condition_met = user.referrals_count >= ach.condition_value
        elif ach.condition_type == 'level':
            condition_met = user.level >= ach.condition_value
        # Добавьте другие типы по необходимости
        
        if condition_met:
            # Выдаём достижение
            ua = UserAchievement(
                user_id=user.id,
                achievement_id=ach.id,
                claimed=False
            )
            session.add(ua)
            
            # Начисляем награду
            if ach.reward_stars > 0:
                user.balance += ach.reward_stars
                # Запись транзакции (можно добавить отдельно)
            if ach.reward_exp > 0:
                add_exp(user, ach.reward_exp)  # функция из leveling.py
                # Обновление уровня будет в leveling
            
            new_achievements.append(ach)
    
    if new_achievements:
        await session.commit()
        logger.info(f"User {user.telegram_id} got new achievements: {[a.name for a in new_achievements]}")
    
    return new_achievements
