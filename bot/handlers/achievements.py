# bot/handlers/achievements.py
from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.main import async_session_maker
from bot.models.db import User
from bot.models.achievement import Achievement, UserAchievement

router = Router()

@router.message(Command("achievements"))
async def cmd_achievements(message: types.Message):
    """Показать список достижений и прогресс"""
    async with async_session_maker() as session:
        # Получаем пользователя
        user = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйся через /start")
            return
        
        # Получаем все достижения пользователя (с данными achievement)
        user_achs = await session.execute(
            select(UserAchievement)
            .where(UserAchievement.user_id == user.id)
            .options(selectinload(UserAchievement.achievement))
        )
        user_achs = user_achs.scalars().all()
        
        # Получаем все достижения для отображения (сортировка по order)
        all_achs = await session.execute(
            select(Achievement).order_by(Achievement.order)
        )
        all_achs = all_achs.scalars().all()
        
        # Составляем словарь полученных
        achieved_dict = {ua.achievement_id: ua for ua in user_achs}
        
        text = "🏆 <b>Ваши достижения</b>\n\n"
        
        for ach in all_achs:
            if ach.id in achieved_dict:
                status = "✅"
                progress = f" (получено {achieved_dict[ach.id].achieved_at.strftime('%d.%m.%Y')})"
            else:
                status = "⬜"
                # Вычисляем прогресс в зависимости от типа условия
                if ach.condition_type == 'total_bets':
                    current = user.total_bets
                elif ach.condition_type == 'total_wins':
                    current = user.total_wins
                elif ach.condition_type == 'total_stars_won':
                    current = user.total_stars_won
                elif ach.condition_type == 'total_stars_bet':
                    current = user.total_stars_bet
                elif ach.condition_type == 'referrals_count':
                    current = user.referrals_count
                elif ach.condition_type == 'level':
                    current = user.level
                else:
                    current = 0
                progress = f" ({current}/{ach.condition_value})"
            
            text += f"{status} <b>{ach.name}</b>{progress}\n{ach.description}\n"
            if ach.reward_stars > 0 or ach.reward_exp > 0:
                text += f"🎁 Награда: {ach.reward_stars}⭐, {ach.reward_exp} опыта\n"
            text += "\n"
        
        await message.answer(text)
