# bot/services/daily_bonus.py

import datetime
import logging
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import async_sessionmaker
from aiogram import Bot

from bot.models.db import User, DailyBonus, Transaction

logger = logging.getLogger(__name__)

async def process_daily_bonuses(session_maker: async_sessionmaker, bot: Bot):
    """
    Проверяет пользователей, которые заходили сегодня, и начисляет им ежедневный бонус.
    Логика: если пользователь заходил сегодня (last_activity >= today) и ещё не получал бонус сегодня,
    то начисляем бонус с учётом streak (серии дней).
    """
    today = datetime.datetime.utcnow().date()
    today_start = datetime.datetime.combine(today, datetime.time.min)
    today_end = datetime.datetime.combine(today, datetime.time.max)

    async with session_maker() as session:
        # Находим всех пользователей, у которых last_activity сегодня
        # и которые ещё не получали бонус сегодня
        users = await session.execute(
            select(User).where(
                User.last_activity >= today_start,
                User.last_activity <= today_end
            )
        )
        users = users.scalars().all()

        for user in users:
            # Проверяем, получал ли бонус сегодня
            bonus_today = await session.execute(
                select(DailyBonus).where(
                    DailyBonus.user_id == user.id,
                    func.date(DailyBonus.bonus_date) == today
                )
            )
            if bonus_today.scalar_one_or_none():
                continue

            # Определяем streak: сколько дней подряд пользователь заходит
            # Для этого нужно посмотреть последний бонус и сравнить дату со вчера
            last_bonus = await session.execute(
                select(DailyBonus)
                .where(DailyBonus.user_id == user.id)
                .order_by(DailyBonus.bonus_date.desc())
                .limit(1)
            )
            last_bonus = last_bonus.scalar_one_or_none()

            if last_bonus and last_bonus.bonus_date.date() == today - datetime.timedelta(days=1):
                streak = last_bonus.streak + 1
            else:
                streak = 1

            # Расчёт бонуса: базовый 50 звёзд + за streak (например, +10 за каждый день, максимум 200)
            base_bonus = 50
            extra = min((streak - 1) * 10, 150)  # максимум 200 всего
            bonus_amount = base_bonus + extra

            # Начисляем
            user.balance += bonus_amount
            user.exp += bonus_amount // 10

            # Запись в daily_bonuses
            bonus_record = DailyBonus(
                user_id=user.id,
                bonus_date=datetime.datetime.utcnow(),
                amount=bonus_amount,
                streak=streak
            )
            session.add(bonus_record)

            # Транзакция
            trans = Transaction(
                user_id=user.id,
                amount=bonus_amount,
                type='daily_bonus',
                description=f'Ежедневный бонус (день {streak})'
            )
            session.add(trans)

            # Отправляем уведомление пользователю
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"🎁 <b>Ежедневный бонус!</b>\n\n"
                    f"Ты получил {bonus_amount} ⭐\n"
                    f"🔥 Серия: {streak} дней\n"
                    f"Продолжай заходить каждый день!"
                )
            except Exception as e:
                logger.error(f"Failed to send daily bonus to {user.telegram_id}: {e}")

            logger.info(f"Daily bonus {bonus_amount} to user {user.telegram_id}, streak {streak}")

        await session.commit()
